#import "OCMItem.h"

@implementation OCMItem

- (nullable instancetype)initWithDictionary:(NSDictionary<NSString *, id> *)dictionary {
    if (![dictionary isKindOfClass:NSDictionary.class]) {
        return nil;
    }

    id rawID = dictionary[@"id"];
    NSString *itemID = nil;
    if ([rawID isKindOfClass:NSString.class]) {
        itemID = rawID;
    } else if ([rawID isKindOfClass:NSNumber.class]) {
        itemID = [(NSNumber *)rawID stringValue];
    }

    id rawTitle = dictionary[@"title"];
    NSString *title = [rawTitle isKindOfClass:NSString.class] ? rawTitle : nil;
    if (itemID.length == 0 || title.length == 0) {
        return nil;
    }

    self = [super init];
    if (self) {
        _itemID = [itemID copy];
        _title = [title copy];

        id rawSubtitle = dictionary[@"subtitle"];
        if ([rawSubtitle isKindOfClass:NSString.class]) {
            _subtitle = [rawSubtitle copy];
        }

        id rawImageURL = dictionary[@"image_url"];
        if ([rawImageURL isKindOfClass:NSString.class]) {
            _imageURL = [NSURL URLWithString:rawImageURL];
        }
    }
    return self;
}

+ (NSArray<OCMItem *> *)itemsFromJSONArray:(id)JSONArray {
    if (![JSONArray isKindOfClass:NSArray.class]) {
        return @[];
    }

    NSMutableArray<OCMItem *> *items = [NSMutableArray array];
    for (id object in (NSArray *)JSONArray) {
        OCMItem *item = [[OCMItem alloc] initWithDictionary:object];
        if (item) {
            [items addObject:item];
        }
    }
    return [items copy];
}

@end
