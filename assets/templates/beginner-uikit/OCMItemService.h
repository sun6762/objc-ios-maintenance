#import <Foundation/Foundation.h>

@class OCMItem;

NS_ASSUME_NONNULL_BEGIN

typedef void (^OCMItemListCompletion)(NSArray<OCMItem *> *_Nullable items, NSError *_Nullable error);

@interface OCMItemService : NSObject

- (instancetype)initWithSession:(NSURLSession *)session baseURL:(NSURL *)baseURL NS_DESIGNATED_INITIALIZER;
- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;

- (NSURLSessionDataTask *)fetchItemsWithCompletion:(OCMItemListCompletion)completion;

@end

NS_ASSUME_NONNULL_END
