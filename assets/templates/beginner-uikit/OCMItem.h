#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface OCMItem : NSObject

@property (nonatomic, copy, readonly) NSString *itemID;
@property (nonatomic, copy, readonly) NSString *title;
@property (nonatomic, copy, readonly, nullable) NSString *subtitle;
@property (nonatomic, copy, readonly, nullable) NSURL *imageURL;

- (instancetype)init NS_UNAVAILABLE;
+ (instancetype)new NS_UNAVAILABLE;

- (nullable instancetype)initWithDictionary:(NSDictionary<NSString *, id> *)dictionary;
+ (NSArray<OCMItem *> *)itemsFromJSONArray:(id)JSONArray;

@end

NS_ASSUME_NONNULL_END
