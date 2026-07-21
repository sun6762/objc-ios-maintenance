//
//  OCMCrashSafety.m
//  Objective-C iOS 崩溃治理模板
//
//  使用原则：
//  1. 不 swizzle，不吞异常，不改变系统类行为。
//  2. helper 只做边界收敛；调用点仍要处理 nil、空数组和空字典。
//  3. 如果需要记录异常上下文，在业务项目中包一层项目自己的日志方法。
//

#import "OCMCrashSafety.h"

void OCMDispatchAsyncOnMainQueue(dispatch_block_t _Nullable block) {
    if (!block) {
        return;
    }

    if ([NSThread isMainThread]) {
        block();
        return;
    }

    dispatch_async(dispatch_get_main_queue(), block);
}

id _Nullable OCMObjectAtIndex(NSArray * _Nullable array, NSUInteger index) {
    if (!array || index >= array.count) {
        return nil;
    }

    return [array subarrayWithRange:NSMakeRange(index, 1)].firstObject;
}

BOOL OCMSetObjectIfValid(NSMutableDictionary * _Nullable dictionary,
                         id<NSCopying> _Nullable key,
                         id _Nullable object) {
    if (!dictionary || !key || !object || object == NSNull.null) {
        return NO;
    }

    dictionary[key] = object;
    return YES;
}

NSString *OCMStringOrEmpty(id _Nullable value) {
    return [value isKindOfClass:NSString.class] ? value : @"";
}

NSArray *OCMArrayOrEmpty(id _Nullable value) {
    return [value isKindOfClass:NSArray.class] ? value : @[];
}

NSDictionary *OCMDictionaryOrEmpty(id _Nullable value) {
    return [value isKindOfClass:NSDictionary.class] ? value : @{};
}
