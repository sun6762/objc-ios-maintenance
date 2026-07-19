#import <Foundation/Foundation.h>

@class OCMItem;

NS_ASSUME_NONNULL_BEGIN

@interface OCMItemCellViewModel : NSObject

@property (nonatomic, copy, readonly) NSString *itemID;
@property (nonatomic, copy, readonly) NSString *titleText;
@property (nonatomic, copy, readonly) NSString *subtitleText;
@property (nonatomic, copy, readonly, nullable) NSURL *imageURL;

- (instancetype)initWithItem:(OCMItem *)item;

@end

@interface OCMItemListViewModel : NSObject

+ (NSArray<OCMItemCellViewModel *> *)cellViewModelsFromItems:(NSArray<OCMItem *> *)items;

@end

NS_ASSUME_NONNULL_END
