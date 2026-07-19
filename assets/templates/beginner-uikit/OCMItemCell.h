#import <UIKit/UIKit.h>

@class OCMItemCellViewModel;

NS_ASSUME_NONNULL_BEGIN

@protocol OCMImageRequest <NSObject>

- (void)cancel;

@end

@protocol OCMImageLoading <NSObject>

- (id<OCMImageRequest>)loadImageWithURL:(NSURL *)URL completion:(void (^)(UIImage *_Nullable image))completion;

@end

@interface OCMItemCell : UITableViewCell

@property (nonatomic, copy, readonly, nullable) NSString *representedItemID;

+ (NSString *)reuseIdentifier;
- (void)configureWithViewModel:(OCMItemCellViewModel *)viewModel imageLoader:(nullable id<OCMImageLoading>)imageLoader;

@end

NS_ASSUME_NONNULL_END
