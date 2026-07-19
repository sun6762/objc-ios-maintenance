#import "OCMItemListViewController.h"
#import "OCMItemCell.h"
#import "OCMItemListViewModel.h"
#import "OCMItemService.h"

@interface OCMItemListViewController () <UITableViewDataSource, UITableViewDelegate>

@property (nonatomic, strong) OCMItemService *service;
@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, copy) NSArray<OCMItemCellViewModel *> *items;
@property (nonatomic, strong, nullable) NSURLSessionDataTask *currentTask;
@property (nonatomic, assign) NSUInteger requestGeneration;

@end

@implementation OCMItemListViewController

- (instancetype)initWithService:(OCMItemService *)service {
    self = [super initWithNibName:nil bundle:nil];
    if (self) {
        _service = service;
        _items = @[];
    }
    return self;
}

- (void)viewDidLoad {
    [super viewDidLoad];

    if (@available(iOS 13.0, *)) {
        self.view.backgroundColor = UIColor.systemBackgroundColor;
    } else {
        self.view.backgroundColor = UIColor.whiteColor;
    }
    [self ocm_setupTableView];
    [self ocm_loadItems];
}

- (void)dealloc {
    [self.currentTask cancel];
}

- (void)ocm_setupTableView {
    UITableView *tableView = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
    tableView.translatesAutoresizingMaskIntoConstraints = NO;
    tableView.dataSource = self;
    tableView.delegate = self;
    tableView.rowHeight = UITableViewAutomaticDimension;
    tableView.estimatedRowHeight = 72.0;
    [tableView registerClass:OCMItemCell.class forCellReuseIdentifier:OCMItemCell.reuseIdentifier];
    [self.view addSubview:tableView];

    [NSLayoutConstraint activateConstraints:@[
        [tableView.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor],
        [tableView.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor],
        [tableView.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor],
        [tableView.bottomAnchor constraintEqualToAnchor:self.view.bottomAnchor],
    ]];

    self.tableView = tableView;
}

- (void)ocm_loadItems {
    [self.currentTask cancel];
    self.requestGeneration += 1;
    NSUInteger generation = self.requestGeneration;

    __weak typeof(self) weakSelf = self;
    self.currentTask = [self.service fetchItemsWithCompletion:^(NSArray<OCMItem *> *items, NSError *error) {
        __strong typeof(weakSelf) self = weakSelf;
        if (!self || generation != self.requestGeneration) {
            return;
        }

        if (error) {
            self.items = @[];
            [self.tableView reloadData];
            return;
        }

        self.items = [OCMItemListViewModel cellViewModelsFromItems:items ?: @[]];
        [self.tableView reloadData];
    }];
}

#pragma mark - UITableViewDataSource

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    return (NSInteger)self.items.count;
}

- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    OCMItemCell *cell = [tableView dequeueReusableCellWithIdentifier:OCMItemCell.reuseIdentifier forIndexPath:indexPath];
    if ((NSUInteger)indexPath.row >= self.items.count) {
        return cell;
    }

    OCMItemCellViewModel *viewModel = self.items[(NSUInteger)indexPath.row];
    [cell configureWithViewModel:viewModel imageLoader:nil];
    return cell;
}

#pragma mark - UITableViewDelegate

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if ((NSUInteger)indexPath.row >= self.items.count) {
        return;
    }

    OCMItemCellViewModel *viewModel = self.items[(NSUInteger)indexPath.row];
    NSLog(@"Selected item: %@", viewModel.itemID);
}

@end
