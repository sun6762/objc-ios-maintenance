//
//  OCMWeakProxy.h
//  Objective-C iOS 维护模板
//
//  这是可复制到业务项目中的模板。复制后建议把 OCM 前缀替换为项目自己的前缀。
//  适用于 NSTimer / CADisplayLink 等会强持有 target 的场景。
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface OCMWeakProxy : NSProxy

+ (instancetype)proxyWithTarget:(id)target;

@property (nonatomic, weak, readonly, nullable) id target;

@end

NS_ASSUME_NONNULL_END
