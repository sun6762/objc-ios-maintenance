//
//  UIView+OCMPerformance.m
//  Objective-C iOS 性能模板
//
//  使用原则：
//  1. 不 swizzle，不自动修改所有 UIView 行为。
//  2. 圆角和阴影优先分层处理：外层 shadow，内层 clips。
//  3. shadowPath 依赖 bounds，应在布局稳定后更新。
//  4. rasterize 只用于复杂但静态的内容，并需要实测收益。
//

#import "UIView+OCMPerformance.h"

static CGFloat OCMClampedCornerRadius(CGFloat cornerRadius, CGRect bounds) {
    CGFloat radius = MAX(0.0, cornerRadius);
    if (CGRectIsEmpty(bounds)) {
        return radius;
    }

    CGFloat maximumRadius = MIN(CGRectGetWidth(bounds), CGRectGetHeight(bounds)) * 0.5;
    return MIN(radius, maximumRadius);
}

static BOOL OCMColorIsFullyOpaque(UIColor *color) {
    CGFloat red = 0.0;
    CGFloat green = 0.0;
    CGFloat blue = 0.0;
    CGFloat alpha = 1.0;

    if ([color getRed:&red green:&green blue:&blue alpha:&alpha]) {
        return alpha >= 1.0;
    }

    CGFloat white = 0.0;
    if ([color getWhite:&white alpha:&alpha]) {
        return alpha >= 1.0;
    }

    return NO;
}

@implementation UIView (OCMPerformance)

- (void)ocm_applyCornerRadius:(CGFloat)cornerRadius clipsToBounds:(BOOL)clipsToBounds {
    self.layer.cornerRadius = OCMClampedCornerRadius(cornerRadius, self.bounds);
    self.layer.masksToBounds = clipsToBounds;
}

- (void)ocm_applyShadowWithColor:(UIColor *)color
                         opacity:(CGFloat)opacity
                          radius:(CGFloat)radius
                          offset:(CGSize)offset {
    self.layer.masksToBounds = NO;
    self.layer.shadowColor = color.CGColor;
    self.layer.shadowOpacity = MAX(0.0, MIN(opacity, 1.0));
    self.layer.shadowRadius = MAX(0.0, radius);
    self.layer.shadowOffset = offset;
}

- (void)ocm_updateShadowPathWithCornerRadius:(CGFloat)cornerRadius {
    if (CGRectIsEmpty(self.bounds)) {
        self.layer.shadowPath = nil;
        return;
    }

    CGFloat radius = OCMClampedCornerRadius(cornerRadius, self.bounds);
    UIBezierPath *path = [UIBezierPath bezierPathWithRoundedRect:self.bounds cornerRadius:radius];
    self.layer.shadowPath = path.CGPath;
}

- (void)ocm_applyShadowWithColor:(UIColor *)color
                         opacity:(CGFloat)opacity
                          radius:(CGFloat)radius
                          offset:(CGSize)offset
                    cornerRadius:(CGFloat)cornerRadius {
    [self ocm_applyShadowWithColor:color opacity:opacity radius:radius offset:offset];
    [self ocm_updateShadowPathWithCornerRadius:cornerRadius];
}

- (void)ocm_configureAsShadowContainerForRoundedContentView:(UIView *)contentView
                                               cornerRadius:(CGFloat)cornerRadius
                                                shadowColor:(UIColor *)shadowColor
                                              shadowOpacity:(CGFloat)shadowOpacity
                                               shadowRadius:(CGFloat)shadowRadius
                                               shadowOffset:(CGSize)shadowOffset {
    [self ocm_applyShadowWithColor:shadowColor
                           opacity:shadowOpacity
                            radius:shadowRadius
                            offset:shadowOffset
                      cornerRadius:cornerRadius];

    [contentView ocm_applyCornerRadius:cornerRadius clipsToBounds:YES];
}

- (void)ocm_applyOpaqueBackgroundColor:(UIColor *)backgroundColor {
    self.backgroundColor = backgroundColor;
    self.opaque = OCMColorIsFullyOpaque(backgroundColor);
}

- (void)ocm_setRasterizationEnabled:(BOOL)enabled {
    self.layer.shouldRasterize = enabled;
    self.layer.rasterizationScale = enabled ? UIScreen.mainScreen.scale : 1.0;
}

@end
