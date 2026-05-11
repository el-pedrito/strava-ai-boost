"""
Frontend Hosting Stack for Strava AI Boost

This stack creates the frontend hosting infrastructure:
- S3 bucket for static website hosting
- CloudFront distribution with OAC
- Cognito User Pool for authentication
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    Duration,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_cognito as cognito,
    aws_iam as iam,
)
from constructs import Construct


class FrontendHostingStack(Stack):
    """Frontend hosting stack with S3, CloudFront, and Cognito"""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 bucket for frontend assets
        self._website_bucket = s3.Bucket(
            self, "WebsiteBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # CloudFront OAC
        oac = cloudfront.CfnOriginAccessControl(
            self, "OAC",
            origin_access_control_config=cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name="StravaAIBoost-OAC",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4",
            ),
        )

        # CloudFront distribution
        self._distribution = cloudfront.Distribution(
            self, "Distribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self._website_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            ),
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
        )

        # Cognito User Pool
        self._user_pool = cognito.UserPool(
            self, "UserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
            custom_attributes={
                "strava_id": cognito.StringAttribute(mutable=True),
            },
        )

        # Cognito User Pool Client (SPA - no secret)
        self._user_pool_client = cognito.UserPoolClient(
            self, "UserPoolClient",
            user_pool=self._user_pool,
            generate_secret=False,
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                custom=False,
                user_password=False,
            ),
        )

        # Outputs
        CfnOutput(self, "DistributionDomain",
                  value=self._distribution.distribution_domain_name)
        CfnOutput(self, "BucketName",
                  value=self._website_bucket.bucket_name)
        CfnOutput(self, "UserPoolId",
                  value=self._user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId",
                  value=self._user_pool_client.user_pool_client_id)
        CfnOutput(self, "DistributionId",
                  value=self._distribution.distribution_id)

    @property
    def website_bucket(self) -> s3.Bucket:
        return self._website_bucket

    @property
    def distribution(self) -> cloudfront.Distribution:
        return self._distribution

    @property
    def user_pool(self) -> cognito.UserPool:
        return self._user_pool

    @property
    def user_pool_client(self) -> cognito.UserPoolClient:
        return self._user_pool_client
