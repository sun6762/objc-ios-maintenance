#import "OCMItemListViewModel.h"
#import "OCMItem.h"

@implementation OCMItemCellViewModel

- (instancetype)initWithItem:(OCMItem *)item {
    self = [super init];
    if (self) {
        _itemID = [item.itemID copy];
        _titleText = [item.title copy];
        _subtitleText = item.subtitle.length > 0 ? [item.subtitle copy] : @"";
        _imageURL = [item.imageURL copy];
    }
    return self;
}

@end

@implementation OCMItemListViewModel

+ (NSArray<OCMItemCellViewModel *> *)cellViewModelsFromItems:(NSArray<OCMItem *> *)items {
    NSMutableArray<OCMItemCellViewModel *> *viewModels = [NSMutableArray arrayWithCapacity:items.count];
    for (OCMItem *item in items) {
        OCMItemCellViewModel *viewModel = [[OCMItemCellViewModel alloc] initWithItem:item];
        [viewModels addObject:viewModel];
    }
    return [viewModels copy];
}

@end
