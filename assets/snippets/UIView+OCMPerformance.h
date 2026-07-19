//
//  UIView+OCMPerformance.h
//  Objective-C iOS 性能模板
//
//  这是可复制到业务项目中的模板。复制后建议把 OCM 前缀替换为项目自己的前缀，
//  以降低 category 方法命名冲突风险。
//

#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

@interface UIView (OCMPerformance)

/// 设置圆角。只有确实需要裁剪子视图时才传 YES。
- (void)ocm_applyCornerRadius:(CGFloat)cornerRadius clipsToBounds:(BOOL)clipsToBounds;

/// 设置阴影参数，但不假设 bounds 已稳定；调用方应在布局后调用 ocm_updateShadowPathWithCornerRadius:。
- (void)ocm_applyShadowWithColor:(UIColor *)color
                         opacity:(CGFloat)opacity
                          radius:(CGFloat)radius
                          offset:(CGSize)offset;

/// 根据当前 bounds 更新 shadowPath。适合在 layoutSubviews / viewDidLayoutSubviews 中按需调用。
- (void)ocm_updateShadowPathWithCornerRadius:(CGFloat)cornerRadius;

/// 设置阴影参数并立即按当前 bounds 更新 shadowPath。只在 bounds 已稳定时使用。
- (void)ocm_applyShadowWithColor:(UIColor *)color
                         opacity:(CGFloat)opacity
                          radius:(CGFloat)radius
                          offset:(CGSize)offset
                    cornerRadius:(CGFloat)cornerRadius;

/// 外层 view 负责阴影，contentView 负责圆角裁剪。适合“圆角 + 阴影”组合。
- (void)ocm_configureAsShadowContainerForRoundedContentView:(UIView *)contentView
                                               cornerRadius:(CGFloat)cornerRadius
                                                shadowColor:(UIColor *)shadowColor
                                              shadowOpacity:(CGFloat)shadowOpacity
                                               shadowRadius:(CGFloat)shadowRadius
                                               shadowOffset:(CGSize)shadowOffset;

/// 设置不透明背景。只有颜色可解析且 alpha 为 1 时才会把 opaque 设为 YES。
- (void)ocm_applyOpaqueBackgroundColor:(UIColor *)backgroundColor;

/// 显式开启或关闭 rasterize。只适合复杂但静态的内容；动态内容不要长期打开。
- (void)ocm_setRasterizationEnabled:(BOOL)enabled;

@end

NS_ASSUME_NONNULL_END
