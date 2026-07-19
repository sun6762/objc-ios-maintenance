#import "OCMItemCell.h"
#import "OCMItemListViewModel.h"

@interface OCMItemCell ()

@property (nonatomic, copy, readwrite, nullable) NSString *representedItemID;
@property (nonatomic, strong, nullable) id<OCMImageRequest> imageRequest;

@end

@implementation OCMItemCell

+ (NSString *)reuseIdentifier {
    return NSStringFromClass(self);
}

- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuseIdentifier {
    self = [super initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:reuseIdentifier];
    if (self) {
        self.selectionStyle = UITableViewCellSelectionStyleNone;
        self.textLabel.numberOfLines = 2;
        self.detailTextLabel.numberOfLines = 2;
    }
    return self;
}

- (void)prepareForReuse {
    [super prepareForReuse];

    [self.imageRequest cancel];
    self.imageRequest = nil;
    self.representedItemID = nil;
    self.textLabel.text = nil;
    self.detailTextLabel.text = nil;
    self.imageView.image = nil;
    self.imageView.hidden = NO;
    self.contentView.alpha = 1.0;
}

- (void)configureWithViewModel:(OCMItemCellViewModel *)viewModel imageLoader:(nullable id<OCMImageLoading>)imageLoader {
    [self.imageRequest cancel];
    self.imageRequest = nil;

    self.representedItemID = viewModel.itemID;
    self.textLabel.text = viewModel.titleText;
    self.detailTextLabel.text = viewModel.subtitleText;
    self.imageView.image = nil;

    if (!viewModel.imageURL || !imageLoader) {
        return;
    }

    NSString *expectedItemID = [viewModel.itemID copy];
    __weak typeof(self) weakSelf = self;
    self.imageRequest = [imageLoader loadImageWithURL:viewModel.imageURL completion:^(UIImage *image) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(weakSelf) self = weakSelf;
            if (!self || ![self.representedItemID isEqualToString:expectedItemID]) {
                return;
            }
            self.imageView.image = image;
            self.imageRequest = nil;
        });
    }];
}

@end
