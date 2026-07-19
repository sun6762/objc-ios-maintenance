#import "OCMItemService.h"
#import "OCMItem.h"

static NSString *const OCMItemServiceErrorDomain = @"com.example.OCMItemService";

typedef NS_ENUM(NSInteger, OCMItemServiceErrorCode) {
    OCMItemServiceErrorCodeInvalidResponse = 1,
    OCMItemServiceErrorCodeInvalidJSON = 2,
};

@interface OCMItemService ()

@property (nonatomic, strong) NSURLSession *session;
@property (nonatomic, copy) NSURL *baseURL;

@end

@implementation OCMItemService

- (instancetype)initWithSession:(NSURLSession *)session baseURL:(NSURL *)baseURL {
    self = [super init];
    if (self) {
        _session = session;
        _baseURL = [baseURL copy];
    }
    return self;
}

- (NSURLSessionDataTask *)fetchItemsWithCompletion:(OCMItemListCompletion)completion {
    NSParameterAssert(completion);

    NSURL *URL = [NSURL URLWithString:@"items" relativeToURL:self.baseURL];
    NSURLRequest *request = [NSURLRequest requestWithURL:URL];

    NSURLSessionDataTask *task = [self.session dataTaskWithRequest:request completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error) {
            [self ocm_dispatchItems:nil error:error completion:completion];
            return;
        }

        NSHTTPURLResponse *HTTPResponse = [response isKindOfClass:NSHTTPURLResponse.class] ? (NSHTTPURLResponse *)response : nil;
        if (!HTTPResponse || HTTPResponse.statusCode < 200 || HTTPResponse.statusCode >= 300 || !data) {
            NSError *responseError = [NSError errorWithDomain:OCMItemServiceErrorDomain
                                                         code:OCMItemServiceErrorCodeInvalidResponse
                                                     userInfo:nil];
            [self ocm_dispatchItems:nil error:responseError completion:completion];
            return;
        }

        NSError *JSONError = nil;
        id JSONObject = [NSJSONSerialization JSONObjectWithData:data options:0 error:&JSONError];
        if (JSONError) {
            [self ocm_dispatchItems:nil error:JSONError completion:completion];
            return;
        }

        id rawItems = [JSONObject isKindOfClass:NSDictionary.class] ? JSONObject[@"items"] : JSONObject;
        NSArray<OCMItem *> *items = [OCMItem itemsFromJSONArray:rawItems];
        if (items.count == 0 && ![rawItems isKindOfClass:NSArray.class]) {
            NSError *parseError = [NSError errorWithDomain:OCMItemServiceErrorDomain
                                                      code:OCMItemServiceErrorCodeInvalidJSON
                                                  userInfo:nil];
            [self ocm_dispatchItems:nil error:parseError completion:completion];
            return;
        }

        [self ocm_dispatchItems:items error:nil completion:completion];
    }];

    [task resume];
    return task;
}

- (void)ocm_dispatchItems:(nullable NSArray<OCMItem *> *)items
                    error:(nullable NSError *)error
               completion:(OCMItemListCompletion)completion {
    dispatch_async(dispatch_get_main_queue(), ^{
        completion(items, error);
    });
}

@end
