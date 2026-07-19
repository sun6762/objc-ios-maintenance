#import <UIKit/UIKit.h>

@class OCMItemService;

NS_ASSUME_NONNULL_BEGIN

@interface OCMItemListViewController : UIViewController

- (instancetype)initWithService:(OCMItemService *)service NS_DESIGNATED_INITIALIZER;
- (instancetype)initWithNibName:(nullable NSString *)nibNameOrNil bundle:(nullable NSBundle *)nibBundleOrNil NS_UNAVAILABLE;
- (instancetype)initWithCoder:(NSCoder *)coder NS_UNAVAILABLE;
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;

@end

NS_ASSUME_NONNULL_END
