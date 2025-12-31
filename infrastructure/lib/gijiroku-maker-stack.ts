import * as cdk from "aws-cdk-lib";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as ssm from "aws-cdk-lib/aws-ssm";
import { Construct } from "constructs";

export class GijirokuMakerStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // Cognito User Pool の作成
    const userPool = new cognito.UserPool(this, "GijirokuMakerUserPool", {
      userPoolName: "gijiroku-maker-user-pool",

      // サインイン設定
      signInAliases: {
        email: true,
        username: false,
        phone: false,
      },

      // 自動検証設定
      autoVerify: {
        email: true, // メール認証を有効
        phone: true, // 電話番号認証も有効
      },

      // 必須属性
      standardAttributes: {
        email: {
          required: true,
          mutable: true,
        },
        givenName: {
          required: true,
          mutable: true,
        },
        familyName: {
          required: true,
          mutable: true,
        },
        phoneNumber: {
          required: true,
          mutable: true,
        },
      },

      // パスワードポリシー
      passwordPolicy: {
        minLength: 8,
        requireLowercase: true,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },

      // MFA設定（SMS認証）
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: {
        sms: true,
        otp: false,
      },

      // アカウント復旧設定
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,

      // セルフサインアップを有効
      selfSignUpEnabled: true,

      // ユーザー招待設定（Admin create user flow用）
      userInvitation: {
        emailSubject: "議事録メーカーへようこそ",
        emailBody:
          "こんにちは {username}さん、議事録メーカーへようこそ！仮パスワード: {####}",
        smsMessage: "ユーザー名: {username} 仮パスワード: {####}",
      },

      // ユーザー検証設定
      userVerification: {
        emailSubject: "議事録メーカー - 確認コード",
        emailBody: "議事録メーカーの確認コード: {####}",
        emailStyle: cognito.VerificationEmailStyle.CODE,
        smsMessage: "議事録メーカーの確認コード: {####}",
      },

      // デバイス設定
      deviceTracking: {
        challengeRequiredOnNewDevice: true,
        deviceOnlyRememberedOnUserPrompt: false,
      },

      // 削除保護
      removalPolicy: cdk.RemovalPolicy.RETAIN,
    });

    // User Pool Client の作成
    const userPoolClient = new cognito.UserPoolClient(
      this,
      "GijirokuMakerUserPoolClient",
      {
        userPool,
        userPoolClientName: "gijiroku-maker-client",

        // 認証フロー設定
        authFlows: {
          userPassword: true,
          userSrp: true,
          custom: false,
          adminUserPassword: false,
        },

        // OAuth設定
        oAuth: {
          flows: {
            authorizationCodeGrant: true,
            implicitCodeGrant: false,
          },
          scopes: [
            cognito.OAuthScope.EMAIL,
            cognito.OAuthScope.OPENID,
            cognito.OAuthScope.PROFILE,
            cognito.OAuthScope.PHONE,
          ],
          callbackUrls: [
            "http://localhost:3001",
            "https://gijiroku-maker.pages.dev", // Cloudflare Pages URL（後で更新）
          ],
          logoutUrls: [
            "http://localhost:3001/login",
            "https://gijiroku-maker.pages.dev/login", // Cloudflare Pages URL（後で更新）
          ],
        },

        // セキュリティ設定
        preventUserExistenceErrors: true,

        // トークン設定
        accessTokenValidity: cdk.Duration.hours(1),
        idTokenValidity: cdk.Duration.hours(1),
        refreshTokenValidity: cdk.Duration.days(30),

        // 読み取り・書き込み属性
        readAttributes: new cognito.ClientAttributes().withStandardAttributes({
          email: true,
          givenName: true,
          familyName: true,
          phoneNumber: true,
        }),
        writeAttributes: new cognito.ClientAttributes().withStandardAttributes({
          email: true,
          givenName: true,
          familyName: true,
          phoneNumber: true,
        }),
      }
    );

    // Identity Pool の作成（必要に応じて）
    const identityPool = new cognito.CfnIdentityPool(
      this,
      "GijirokuMakerIdentityPool",
      {
        identityPoolName: "gijiroku-maker-identity-pool",
        allowUnauthenticatedIdentities: false,
        cognitoIdentityProviders: [
          {
            clientId: userPoolClient.userPoolClientId,
            providerName: userPool.userPoolProviderName,
          },
        ],
      }
    );

    // Systems Manager Parameter Store に値を保存
    new ssm.StringParameter(this, "CognitoUserPoolId", {
      parameterName: "/gijiroku-maker/cognito/user-pool-id",
      stringValue: userPool.userPoolId,
      description: "議事録メーカー Cognito User Pool ID",
    });

    new ssm.StringParameter(this, "CognitoClientId", {
      parameterName: "/gijiroku-maker/cognito/client-id",
      stringValue: userPoolClient.userPoolClientId,
      description: "議事録メーカー Cognito Client ID",
    });

    new ssm.StringParameter(this, "CognitoIdentityPoolId", {
      parameterName: "/gijiroku-maker/cognito/identity-pool-id",
      stringValue: identityPool.ref,
      description: "議事録メーカー Cognito Identity Pool ID",
    });

    // CloudFormation Outputs
    new cdk.CfnOutput(this, "UserPoolId", {
      value: userPool.userPoolId,
      description: "Cognito User Pool ID",
      exportName: "GijirokuMaker-UserPoolId",
    });

    new cdk.CfnOutput(this, "UserPoolClientId", {
      value: userPoolClient.userPoolClientId,
      description: "Cognito User Pool Client ID",
      exportName: "GijirokuMaker-UserPoolClientId",
    });

    new cdk.CfnOutput(this, "IdentityPoolId", {
      value: identityPool.ref,
      description: "Cognito Identity Pool ID",
      exportName: "GijirokuMaker-IdentityPoolId",
    });

    new cdk.CfnOutput(this, "Region", {
      value: this.region,
      description: "AWS Region",
      exportName: "GijirokuMaker-Region",
    });
  }
}
