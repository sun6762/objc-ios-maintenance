# 滚动性能

当任务涉及 UITableView/UICollectionView 滚动掉帧、cell 复用、异步图片、图片预解码、约束复用、高度缓存、prefetch、列表刷新卡顿或旧 Objective-C 列表性能优化时读取本文件。

## 快速目录

- 判断顺序
- Cell 复用
- 异步图片
- 图片预解码
- 约束复用
- 高度缓存
- 预估行高
- Prefetch
- 列表刷新
- 不适用场景
- 审查清单

## 判断顺序

滚动性能问题不要只看 cell 代码。先按下面顺序定位：

1. 主线程是否被阻塞：同步网络、磁盘 IO、JSON 解析、图片解码、Auto Layout 大量计算。
2. cell 是否正确复用：状态是否重置，异步任务是否取消，旧回调是否会污染新 model。
3. 图片是否按展示尺寸加载和解码：是否加载原图、主线程解码、重复处理圆角。
4. 布局是否稳定：约束是否重复创建，高度是否频繁计算，动态高度是否缓存。
5. 数据更新是否合理：是否全量 `reloadData`，是否在滚动中做大批量同步更新。
6. 是否使用 prefetch：是否提前加载即将出现的数据，并取消不再需要的预取。

先用 Instruments / Time Profiler / Core Animation 或滚动 FPS 确认瓶颈，再修改代码。不要把所有问题都归因于离屏渲染。

## Cell 复用

cell 配置必须是幂等的：同一个 cell 被不同 model 重复配置后，不能残留旧状态。

### 复用标识符与注册

复用标识符只应该描述“同一类视图/同一布局”，不要把 model identifier 当成复用标识符。注册和 dequeue 必须成对出现，且字符串保持完全一致。

```objc
static NSString * const FeedCellReuseIdentifier = @"FeedCell";

- (void)viewDidLoad {
    [super viewDidLoad];

    [self.tableView registerClass:FeedCell.class
           forCellReuseIdentifier:FeedCellReuseIdentifier];
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    FeedCell *cell = [tableView dequeueReusableCellWithIdentifier:FeedCellReuseIdentifier
                                                     forIndexPath:indexPath];
    [cell configureWithItem:self.items[indexPath.row]];
    return cell;
}
```

如果使用 XIB：

```objc
[self.tableView registerNib:[UINib nibWithNibName:@"FeedCell" bundle:nil]
     forCellReuseIdentifier:FeedCellReuseIdentifier];
```

UICollectionView 的写法类似：

```objc
[self.collectionView registerClass:FeedCell.class
        forCellWithReuseIdentifier:FeedCellReuseIdentifier];

FeedCell *cell = [collectionView dequeueReusableCellWithReuseIdentifier:FeedCellReuseIdentifier
                                                           forIndexPath:indexPath];
```

注意：

- 同一个 identifier 只对应同一类 cell / 同一套布局。
- register 和 dequeue 的 identifier 必须一致。
- 不要在 dequeue 失败后手动 `alloc/init` 兜底；这通常表示注册缺失或 identifier 写错。
- 多种 cell 类型时，为不同布局分别定义常量，而不是靠字符串散落在各处。

`prepareForReuse` 中至少考虑：

- 取消异步图片、网络、数据库或富文本生成任务。
- 清空图片、文本、进度、错误态、选中态、hidden、alpha、transform。
- 重置 delegate/block 回调中绑定的 model 标识。
- 清理一次性动画、timer、display link。
- 不要移除并重建固定约束；只重置 constraint constant 或状态。

```objc
@interface FeedCell ()
@property (nonatomic, copy, nullable) NSString *representedIdentifier;
@property (nonatomic, strong, nullable) NSURLSessionDataTask *imageTask;
@end

@implementation FeedCell

- (void)prepareForReuse {
    [super prepareForReuse];

    [self.imageTask cancel];
    self.imageTask = nil;
    self.representedIdentifier = nil;

    self.titleLabel.text = nil;
    self.avatarImageView.image = nil;
    self.avatarImageView.alpha = 1.0;
    self.badgeView.hidden = YES;
}

- (void)configureWithItem:(FeedItem *)item imageLoader:(ImageLoader *)imageLoader {
    self.representedIdentifier = item.identifier;
    self.titleLabel.text = item.title;
    self.badgeView.hidden = !item.hasBadge;
    self.avatarImageView.image = nil;

    __weak typeof(self) weakSelf = self;
    self.imageTask = [imageLoader loadImageWithURL:item.avatarURL completion:^(UIImage *image, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(weakSelf) self = weakSelf;
            if (!self) {
                return;
            }
            if (![self.representedIdentifier isEqualToString:item.identifier]) {
                return;
            }
            self.avatarImageView.image = image;
        });
    }];
}

@end
```

不要只依赖 indexPath 判断旧回调，因为插入、删除、排序后 indexPath 会变化。优先使用稳定的 model identifier。

## 异步图片

列表图片性能的核心是“尺寸正确、后台解码、可取消、可缓存、回主线程更新 UI”。

审查点：

- 不要在 cell 中同步读取磁盘或网络图片。
- 不要把超大原图直接塞给小尺寸 imageView。
- 下载、磁盘读取、缩放、解码应在后台队列完成。
- completion 回到主线程前，要确认 cell 仍代表同一个 model。
- 使用内存缓存时，key 应包含 URL、目标尺寸、scale、圆角或处理参数。
- 对同一 URL 的重复请求应合并或命中缓存。

```objc
typedef void (^ImageCompletion)(UIImage * _Nullable image, NSError * _Nullable error);

- (NSURLSessionDataTask *)loadImageWithURL:(NSURL *)URL
                                targetSize:(CGSize)targetSize
                                completion:(ImageCompletion)completion {
    UIImage *cachedImage = [self.cache objectForKey:[self cacheKeyForURL:URL targetSize:targetSize]];
    if (cachedImage) {
        dispatch_async(dispatch_get_main_queue(), ^{
            completion(cachedImage, nil);
        });
        return nil;
    }

    NSURLSessionDataTask *task = [self.session dataTaskWithURL:URL
                                             completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                completion(nil, error);
            });
            return;
        }

        UIImage *image = [UIImage imageWithData:data];
        UIImage *decodedImage = [self decodedImageFromImage:image targetSize:targetSize];
        if (decodedImage) {
            [self.cache setObject:decodedImage forKey:[self cacheKeyForURL:URL targetSize:targetSize]];
        }

        dispatch_async(dispatch_get_main_queue(), ^{
            completion(decodedImage, nil);
        });
    }];
    [task resume];
    return task;
}
```

## 图片预解码

图片第一次显示时可能在主线程触发解码，造成滚动瞬间卡顿。对列表中的大图、圆角图、缩略图，优先在后台队列按展示尺寸预解码。

使用 `UIGraphicsImageRenderer` 的示例：

```objc
- (nullable UIImage *)decodedImageFromImage:(UIImage *)image targetSize:(CGSize)targetSize {
    if (!image || targetSize.width <= 0.0 || targetSize.height <= 0.0) {
        return nil;
    }

    UIGraphicsImageRendererFormat *format = [UIGraphicsImageRendererFormat preferredFormat];
    format.scale = UIScreen.mainScreen.scale;
    format.opaque = NO;

    UIGraphicsImageRenderer *renderer = [[UIGraphicsImageRenderer alloc] initWithSize:targetSize format:format];
    return [renderer imageWithActions:^(UIGraphicsImageRendererContext *context) {
        [image drawInRect:CGRectMake(0.0, 0.0, targetSize.width, targetSize.height)];
    }];
}
```

注意：

- 预解码要在后台队列运行。
- targetSize 应是展示尺寸，不要无意义地解码原图尺寸。
- 如果图片不需要透明，使用 opaque renderer 可以减少混合成本。
- 圆角图片可以在预处理阶段绘制成圆角 bitmap，但要把圆角半径纳入缓存 key。
- 大量预解码会增加内存压力，要配合 `NSCache` 和内存警告清理。

## 约束复用

滚动列表中最常见的 Auto Layout 问题是重复创建约束，尤其是在 `cellForRow`、`configure`、`layoutSubviews` 中反复 `activateConstraints:`。

规则：

- 固定约束在 `init` / `awakeFromNib` / `setupViews` 中创建一次。
- 需要变化的布局保留 constraint 引用，只改 `constant` 或 `active`。
- 不要在 `layoutSubviews` 里添加相同约束。
- 不要在每次 `configure` 中 remove all constraints 再重建。
- 复杂 cell 可以拆成固定布局层和可隐藏内容层，减少约束组合爆炸。

```objc
@interface FeedCell ()
@property (nonatomic, strong) NSLayoutConstraint *badgeWidthConstraint;
@end

- (void)setupConstraints {
    self.badgeWidthConstraint = [self.badgeView.widthAnchor constraintEqualToConstant:0.0];

    [NSLayoutConstraint activateConstraints:@[
        self.badgeWidthConstraint,
        [self.titleLabel.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:16.0],
        [self.titleLabel.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-16.0]
    ]];
}

- (void)configureWithItem:(FeedItem *)item {
    self.badgeView.hidden = !item.hasBadge;
    self.badgeWidthConstraint.constant = item.hasBadge ? 18.0 : 0.0;
}
```

如果使用 Masonry/SnapKit 的 Objective-C 旧代码，也遵循同样原则：初始化时 `makeConstraints`，状态变化时 `updateConstraints`，避免高频 `remakeConstraints`。

## 高度缓存

动态高度 cell 如果每次滚动都重新计算，容易造成主线程抖动。高度缓存要有稳定 key 和明确失效条件。

缓存 key 建议包含：

- model identifier。
- 内容版本，例如文本 hash、图片比例、展开/折叠状态。
- 宽度，因为横竖屏、分屏、不同设备宽度会改变高度。
- Dynamic Type 或字体配置版本。

```objc
- (NSString *)heightCacheKeyForItem:(FeedItem *)item width:(CGFloat)width {
    return [NSString stringWithFormat:@"%@-%0.f-%lu-%@",
            item.identifier,
            width,
            (unsigned long)item.contentHash,
            self.traitCollection.preferredContentSizeCategory];
}
```

使用缓存：

```objc
- (CGFloat)tableView:(UITableView *)tableView heightForRowAtIndexPath:(NSIndexPath *)indexPath {
    FeedItem *item = self.items[indexPath.row];
    NSString *key = [self heightCacheKeyForItem:item width:CGRectGetWidth(tableView.bounds)];
    NSNumber *cachedHeight = [self.heightCache objectForKey:key];
    if (cachedHeight) {
        return cachedHeight.doubleValue;
    }

    CGFloat height = [self.heightCalculator heightForItem:item width:CGRectGetWidth(tableView.bounds)];
    [self.heightCache setObject:@(height) forKey:key];
    return height;
}
```

失效条件：

- 数据内容变化。
- 列表宽度变化。
- 字体、Dynamic Type、语言、布局方向变化。
- cell 展开/折叠状态变化。

## 预估行高

预估行高不是必须开启的。它的价值是帮助系统更快预排版；如果估算太差，反而会带来滚动条跳动和额外修正。

```objc
// 固定高度列表
self.tableView.rowHeight = 56.0;
self.tableView.estimatedRowHeight = 0.0;

// 自适应高度列表
self.tableView.rowHeight = UITableViewAutomaticDimension;
self.tableView.estimatedRowHeight = 88.0;
```

使用建议：

- 高度固定或变化很小的列表：直接用固定 `rowHeight`，不需要复杂估算。
- 自适应高度列表：`estimatedRowHeight` 应尽量接近真实平均值。
- 内容差异很大、首帧跳动明显的列表：可以实现 `tableView:estimatedHeightForRowAtIndexPath:`，用缓存值或分桶估算。
- 如果估算收益不明显、反而造成频繁修正，就降低估算复杂度，甚至关闭估算。

```objc
- (CGFloat)tableView:(UITableView *)tableView estimatedHeightForRowAtIndexPath:(NSIndexPath *)indexPath {
    FeedItem *item = self.items[indexPath.row];
    NSNumber *cachedHeight = [self.heightCache objectForKey:[self heightCacheKeyForItem:item width:CGRectGetWidth(tableView.bounds)]];
    if (cachedHeight) {
        return cachedHeight.doubleValue;
    }
    return item.hasLongText ? 120.0 : 72.0;
}
```

UICollectionView 的 self-sizing cell 也要谨慎使用 `estimatedItemSize`：如果布局会反复重算，优先换成稳定 item size 或缓存后的尺寸。

## Prefetch

`UITableViewDataSourcePrefetching` 和 `UICollectionViewDataSourcePrefetching` 适合提前发起图片、数据或高度计算任务。prefetch 必须支持取消，否则快速滑动时会制造更多无用工作。

```objc
@interface FeedViewController () <UITableViewDataSourcePrefetching>
@property (nonatomic, strong) NSMutableDictionary<NSIndexPath *, NSURLSessionDataTask *> *prefetchTasks;
@end

- (void)viewDidLoad {
    [super viewDidLoad];
    self.tableView.prefetchDataSource = self;
    self.prefetchTasks = [NSMutableDictionary dictionary];
}

- (void)tableView:(UITableView *)tableView prefetchRowsAtIndexPaths:(NSArray<NSIndexPath *> *)indexPaths {
    for (NSIndexPath *indexPath in indexPaths) {
        if (indexPath.row >= self.items.count) {
            continue;
        }
        FeedItem *item = self.items[indexPath.row];
        NSURLSessionDataTask *task = [self.imageLoader loadImageWithURL:item.avatarURL
                                                             targetSize:CGSizeMake(44.0, 44.0)
                                                             completion:^(UIImage *image, NSError *error) {
            // 这里只预热缓存，不直接更新 UI。
        }];
        if (task) {
            self.prefetchTasks[indexPath] = task;
        }
    }
}

- (void)tableView:(UITableView *)tableView cancelPrefetchingForRowsAtIndexPaths:(NSArray<NSIndexPath *> *)indexPaths {
    for (NSIndexPath *indexPath in indexPaths) {
        [self.prefetchTasks[indexPath] cancel];
        [self.prefetchTasks removeObjectForKey:indexPath];
    }
}
```

更稳的实现应使用 model identifier 作为任务 key，而不是只用 indexPath；当数据源会插入、删除、重排时尤其如此。

## 列表刷新

滚动过程中避免无差别 `reloadData`。优先选择语义明确的更新：

- 单个 item 变化：`reloadRowsAtIndexPaths:` 或 reload item。
- 批量插入/删除：使用 batch updates，并确保数据源先更新。
- 大范围重排：考虑 diff 算法或分段刷新。
- 正在滚动时的非关键 UI 更新：延后到滚动停止或下一轮 run loop。

不要在 `scrollViewDidScroll:` 中做重活：

- 不要同步读写磁盘。
- 不要解析 JSON。
- 不要创建大量 attributed string。
- 不要触发全量布局。
- 不要频繁发网络请求。

## 不适用场景

不要把本文件当成“所有列表都要套一遍优化”的清单：

- 列表数据量很小、无掉帧证据时，不需要提前引入高度缓存、prefetch 或复杂图片管线。
- cell 高度固定时，不需要自适应高度和复杂估算。
- 图片已经由成熟库处理尺寸、缓存、取消和解码时，优先检查库配置和调用方式，不要重复造一套 loader。
- `reloadData` 对小列表或低频状态切换可能足够清晰；只有热路径卡顿或状态丢失时再改为局部刷新/diff。
- prefetch 不能替代 cell 复用清理。预取任务不可取消时，prefetch 可能让快速滑动更慢。

## 审查清单

- 复用：`prepareForReuse` 是否取消旧任务并重置所有可见状态？
- 旧回调：异步 completion 是否检查稳定 model identifier？
- 图片：是否按展示尺寸加载、缩放、后台解码并缓存？
- 主线程：是否避免在主线程做 IO、解码、JSON、复杂文本排版？
- 约束：固定约束是否只创建一次，动态布局是否只改 constant/active？
- 高度：动态高度是否缓存，缓存 key 是否包含宽度和内容版本？
- Prefetch：是否提前预热数据/图片，高速滑动时是否取消预取？
- 刷新：是否避免滚动中全量 `reloadData` 或大批量同步更新？
- 验证：是否用 Time Profiler、Core Animation 或 FPS 数据确认优化有效？
