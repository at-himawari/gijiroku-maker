#!/usr/bin/env node
import "source-map-support/register";
import * as cdk from "aws-cdk-lib";
import { GijirokuMakerStack } from "../lib/gijiroku-maker-stack";

const app = new cdk.App();

// 環境設定
const env = {
  account: process.env.CDK_DEFAULT_ACCOUNT,
  region: process.env.CDK_DEFAULT_REGION || "ap-northeast-1",
};

new GijirokuMakerStack(app, "GijirokuMakerStack", {
  env,
  description: "議事録メーカーのインフラストラクチャスタック",
});
