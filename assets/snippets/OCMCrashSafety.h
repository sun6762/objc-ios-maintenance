//
//  OCMCrashSafety.h
//  Objective-C iOS 崩溃治理模板
//
//  这是可复制到业务项目中的模板。复制后建议把 OCM 前缀替换为项目自己的前缀。
//  只提供显式调用的边界 helper，不修改 Foundation/UIKit 全局行为。
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// 在主线程执行 block。已在主线程时同步执行，避免额外 run loop 延迟。
FOUNDATION_EXPORT void OCMDispatchAsyncOnMainQueue(dispatch_block_t _Nullable block);

/// 带边界检查的数组读取。越界返回 nil，调用点必须处理空状态。
FOUNDATION_EXPORT id _Nullable OCMObjectAtIndex(NSArray * _Nullable array, NSUInteger index);

/// 仅当 key 和 object 都有效时写入字典。object 为 nil 或 NSNull 时返回 NO。
FOUNDATION_EXPORT BOOL OCMSetObjectIfValid(NSMutableDictionary * _Nullable dictionary,
                                           id<NSCopying> _Nullable key,
                                           id _Nullable object);

/// 外部数据类型收敛。类型不匹配时返回空值，不把 NSNull 传入 UI 层。
FOUNDATION_EXPORT NSString *OCMStringOrEmpty(id _Nullable value);
FOUNDATION_EXPORT NSArray *OCMArrayOrEmpty(id _Nullable value);
FOUNDATION_EXPORT NSDictionary *OCMDictionaryOrEmpty(id _Nullable value);

NS_ASSUME_NONNULL_END
