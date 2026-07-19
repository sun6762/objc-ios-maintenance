//
//  OCMWeakProxy.m
//  Objective-C iOS 维护模板
//
//  weak proxy 只能打断 target 循环引用，不能替代 invalidate。
//

#import "OCMWeakProxy.h"

#include <stdlib.h>

@interface OCMWeakProxy ()
@property (nonatomic, weak, readwrite, nullable) id target;
@end

@implementation OCMWeakProxy

+ (instancetype)proxyWithTarget:(id)target {
    OCMWeakProxy *proxy = [OCMWeakProxy alloc];
    proxy.target = target;
    return proxy;
}

- (NSMethodSignature *)methodSignatureForSelector:(SEL)selector {
    NSMethodSignature *signature = [self.target methodSignatureForSelector:selector];
    if (signature) {
        return signature;
    }
    return [NSObject instanceMethodSignatureForSelector:@selector(init)];
}

- (void)forwardInvocation:(NSInvocation *)invocation {
    id target = self.target;
    if (target && [target respondsToSelector:invocation.selector]) {
        [invocation invokeWithTarget:target];
        return;
    }

    NSUInteger returnLength = invocation.methodSignature.methodReturnLength;
    if (returnLength > 0) {
        void *buffer = calloc(1, returnLength);
        [invocation setReturnValue:buffer];
        free(buffer);
    }
}

- (BOOL)respondsToSelector:(SEL)selector {
    return [self.target respondsToSelector:selector] || [super respondsToSelector:selector];
}

- (BOOL)isEqual:(id)object {
    return [self.target isEqual:object];
}

- (NSUInteger)hash {
    return [self.target hash];
}

- (Class)class {
    return [self.target class];
}

- (Class)superclass {
    return [self.target superclass];
}

- (BOOL)isKindOfClass:(Class)aClass {
    return [self.target isKindOfClass:aClass];
}

- (BOOL)isMemberOfClass:(Class)aClass {
    return [self.target isMemberOfClass:aClass];
}

- (NSString *)description {
    return [self.target description];
}

@end
