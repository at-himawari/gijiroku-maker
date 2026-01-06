"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  MicIcon,
  SquareIcon,
  DownloadIcon,
  LogOutIcon,
  CreditCardIcon,
  RefreshCwIcon,
  AlertCircleIcon,
  ClockIcon,
  PlusIcon,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/contexts/AuthContext";
import { fetchAuthSession } from "aws-amplify/auth";
import Image from "next/image";
import { useUserProfile } from "@/hooks/useUserProfile";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"; // 追加

const SAMPLE_RATE = 16000;
const WS_URL = process.env.NEXT_PUBLIC_WS_BASE_URL!;
// APIのベースURL
const API_BASE_URL = process.env.NEXT_PUBLIC_HOST!;

const WORKLET_CODE = `
class RecorderProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 1024;
    this.buffer = new Float32Array(this.bufferSize);
    this.bufferIndex = 0;
  }

  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input && input.length > 0) {
      const channelData = input[0];
      for (let i = 0; i < channelData.length; i++) {
        this.buffer[this.bufferIndex++] = channelData[i];
        if (this.bufferIndex === this.bufferSize) {
          // バッファがいっぱいになったらメインスレッドへ送信
          this.port.postMessage(this.buffer.slice());
          this.bufferIndex = 0;
        }
      }
    }
    return true; // プロセッサーを維持
  }
}
registerProcessor('recorder-processor', RecorderProcessor);
`;

// グローバルなWebSocket管理（Reactの再レンダリングに影響されない）
let globalWebSocket: WebSocket | null = null;
let isExplicitlyClosing = false;

export default function TranscriptionApp() {
  const [isRecording, setIsRecording] = useState(false);
  const [minutes, setMinutes] = useState<string>("");
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<AudioWorkletNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [allTranscript, setAllTranscript] = useState<string>("");
  const [immediate, setImmediate] = useState<string>("");
  const [connectionStatus, setConnectionStatus] = useState<
    "disconnected" | "connecting" | "connected" | "error"
  >("disconnected");
  // 残高（秒）の状態管理
  const [balance, setBalance] = useState<number | null>(null);
  const { toast } = useToast();
  const { logout, token, user } = useAuth();

  // ★課金情報取得用のフックを使用
  const {
    profile,
    fetchProfile,
    loading: profileLoading,
    error: profileError,
  } = useUserProfile();

  // プロフィール読み込み時に残高をstateにセット
  useEffect(() => {
    if (profile) {
      const receivedBalance =
        profile.seconds_balance ?? (profile as any).secondsBalance;
      setBalance(receivedBalance);
    }
  }, [profile]);

  const handleBuyCredits = async () => {
    if (!token) return;
    try {
      const response = await fetch(
        `${API_BASE_URL}/payment/create-checkout-session`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ quantity: 1 }), // 30分 x 1
        }
      );
      const data = await response.json();
      if (data.url) {
        window.location.href = data.url;
      } else {
        toast({
          title: "エラー",
          description: "決済ページの取得に失敗しました",
          variant: "destructive",
        });
      }
    } catch (e) {
      console.error(e);
      toast({
        title: "エラー",
        description: "通信エラーが発生しました",
        variant: "destructive",
      });
    }
  };

  // 秒数を「分:秒」形式に変換する関数
  const formatSeconds = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}分${s}秒`;
  };

  useEffect(() => {
    if (token) {
      fetchProfile();
    }
  }, [token, fetchProfile]);

  const connectWebSocket = useCallback(() => {
    // 既に接続中または接続試行中の場合は何もしない
    if (globalWebSocket) {
      if (
        globalWebSocket.readyState === WebSocket.OPEN ||
        globalWebSocket.readyState === WebSocket.CONNECTING
      ) {
        return;
      }
    }

    if (!token) return;

    setConnectionStatus("connecting");
    isExplicitlyClosing = false;

    const wsUrl = WS_URL;
    console.log("WebSocket接続を開始します:", wsUrl);
    globalWebSocket = new WebSocket(wsUrl, "cognito-auth");

    globalWebSocket.onopen = async () => {
      console.log("WebSocket接続が確立されました:", wsUrl);
      try {
        // 常に最新のセッションからトークンを取得し直す
        const session = await fetchAuthSession();
        const latestToken = session.tokens?.accessToken?.toString();

        if (globalWebSocket && latestToken) {
          console.log("最新のトークンで認証メッセージを送信します");
          globalWebSocket.send(
            JSON.stringify({
              type: "auth",
              token: latestToken,
            })
          );
        }
      } catch (err) {
        console.error("トークン取得エラー:", err);
      }
      setConnectionStatus("connected");
    };

    globalWebSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        // 認証失敗（トークン切れなど）の場合の処理
        if (data.type === "error" && data.message === "認証失敗") {
          toast({
            title: "認証エラー",
            description:
              "WebSocket認証に失敗しました。詳細をコンソールで確認してください。",
            variant: "destructive",
          });
          console.error("WebSocket認証失敗:", data.message);
          return;
        }

        if (data.type === "transcription") {
          setAllTranscript((prev) => `${prev} ${data.text}`);
        } else if (data.type === "immediate") {
          setImmediate(data.text);
        } else if (data.type === "minutes") {
          setMinutes(data.text);
        } else if (data.type === "error") {
          toast({
            title: "エラー",
            description: data.message,
            variant: "destructive",
          });
        }
      } catch (error) {
        console.error("WebSocketメッセージ解析エラー:", error);
      }
    };

    globalWebSocket.onerror = (error) => {
      if (!isExplicitlyClosing) {
        console.error("WebSocketエラー詳細:", error);
        setConnectionStatus("error");
      }
    };

    globalWebSocket.onclose = (event) => {
      if (isExplicitlyClosing) {
        console.log("WebSocketは意図的に閉じられました");
      } else {
        console.log("WebSocket接続が閉じられました:", event.code, event.reason);
        setConnectionStatus("disconnected");

        // 認証エラーによる切断（4001など）の場合の処理
        if (event.code === 4001) {
          toast({
            title: "認証エラー",
            description: "WebSocket接続が認証エラーで切断されました。",
            variant: "destructive",
          });
          console.error("WebSocket切断(4001): 認証エラー");
          // デバッグのため強制ログアウトを一時停止
          // logout();
          return;
        }

        // 録音中かつ予期せぬ切断の場合は再接続を試行
        if (event.code !== 1000 && event.code !== 1001) {
          setTimeout(connectWebSocket, 3000);
        }
      }
    };
  }, [token, toast]);

  useEffect(() => {
    if (token) {
      connectWebSocket();
    } else {
      if (globalWebSocket) {
        isExplicitlyClosing = true;
        globalWebSocket.close(1000, "ログアウト");
        globalWebSocket = null;
      }
      setConnectionStatus("disconnected");
    }

    // アンマウント時の処理を厳密にする
    return () => {
      // 実際にはシングルトンなので閉じない方が安定するが、
      // ログアウト時などは明示的に閉じる必要がある
    };
  }, [token, connectWebSocket]);

  const startRecording = async () => {
    try {
      if (connectionStatus !== "connected") {
        toast({
          title: "接続エラー",
          description: "サーバーに接続されていません。再接続を待ってください。",
          variant: "destructive",
        });
        return;
      }

      // 残高チェック
      if (balance !== null && balance <= 0) {
        toast({
          title: "残高不足",
          description:
            "利用可能時間がありません。クレジットを購入してください。",
          variant: "destructive",
        });
        return;
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      audioContextRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
      const blob = new Blob([WORKLET_CODE], { type: "application/javascript" });
      const workletUrl = URL.createObjectURL(blob);
      await audioContextRef.current.audioWorklet.addModule(workletUrl);
      sourceRef.current =
        audioContextRef.current.createMediaStreamSource(stream);

      const processor = new AudioWorkletNode(
        audioContextRef.current,
        "recorder-processor"
      );
      processorRef.current = processor;

      processor.port.onmessage = (e) => {
        if (globalWebSocket?.readyState === WebSocket.OPEN) {
          const audioData = convertFloat32ToInt16(e.data);
          globalWebSocket.send(audioData);
        }
      };

      sourceRef.current.connect(processorRef.current);
      processorRef.current.connect(audioContextRef.current.destination);

      setIsRecording(true);
      URL.revokeObjectURL(workletUrl);
    } catch (error) {
      console.error("Error accessing microphone:", error);
      toast({
        title: "エラー",
        description: "マイクへのアクセスに失敗しました。",
        variant: "destructive",
      });
    }
  };

  const stopRecording = () => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioContextRef.current) {
      sourceRef.current?.disconnect();
      processorRef.current?.disconnect();
      processorRef.current = null;
      audioContextRef.current.close();
    }
    setIsRecording(false);
  };

  const generateMinutes = async () => {
    if (!token) return;
    try {
      const response = await fetch(`${API_BASE_URL}/generate_minutes`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          transcript: allTranscript,
        }),
      });

      if (!response.ok) throw new Error("Minutes generation failed");
      const data = await response.json();
      setMinutes(data.minutes);

      // 議事録生成成功時に使用回数を更新するため再取得
      await fetchProfile();

      toast({ title: "成功", description: "議事録が生成されました。" });
    } catch (error) {
      console.error("Error generating minutes:", error);
      toast({
        title: "エラー",
        description: "議事録の生成に失敗しました。",
        variant: "destructive",
      });
    }
  };

  const downloadMinutes = () => {
    const element = document.createElement("a");
    const file = new Blob([minutes], { type: "text/plain" });
    element.href = URL.createObjectURL(file);
    element.download = "meeting_minutes.txt";
    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);
  };

  const convertFloat32ToInt16 = (buffer: Float32Array) => {
    const l = buffer.length;
    const buf = new Int16Array(l);
    for (let i = 0; i < l; i++) {
      buf[i] = Math.min(1, buffer[i]) * 0x7fff;
    }
    return buf.buffer;
  };

  return (
    <div className="container mx-auto">
      {/* エラーがある場合はアラートを表示 */}
      {profileError && (
        <Alert variant="destructive" className="mb-4">
          <AlertCircleIcon className="h-4 w-4" />
          <AlertTitle>プロフィール取得エラー</AlertTitle>
          <AlertDescription>
            {profileError} (再読み込みを試してください)
          </AlertDescription>
        </Alert>
      )}
      <div className="flex">
        <div className="flex items-center mb-4">
          <Image width={30} height={30} src="/logo.png" alt="logo" />
          <h1 className="text-2xl font-bold ml-2">
            リアルタイム議事録システム
          </h1>
        </div>
        <div className="flex justify-between items-center border-b-2 border-yellow-400 mb-2">
          <div className="flex items-center"></div>
          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2">
              <div
                className={`w-3 h-3 rounded-full ${
                  connectionStatus === "connected"
                    ? "bg-green-500"
                    : connectionStatus === "connecting"
                    ? "bg-yellow-500 animate-pulse"
                    : "bg-red-500"
                }`}
              ></div>
              <span className="text-sm text-gray-600">
                {connectionStatus === "connected"
                  ? "接続済み"
                  : connectionStatus === "connecting"
                  ? "接続中..."
                  : "未接続"}
              </span>
            </div>
            {user && (
              <div className="text-sm text-gray-600">{user.email} さん</div>
            )}
            <Button
              onClick={async () => {
                isExplicitlyClosing = true;
                if (globalWebSocket) globalWebSocket.close();
                globalWebSocket = null;
                if (isRecording) stopRecording();
                logout();
              }}
              variant="outline"
              size="sm"
            >
              <LogOutIcon className="w-4 h-4 mr-2" />
              ログアウト
            </Button>
          </div>
        </div>
      </div>
      {profileLoading && !profile ? (
        <div className="flex items-center bg-gray-100 rounded-lg px-3 py-1 text-sm space-x-3 text-gray-400">
          読み込み中...
        </div>
      ) : profile ? (
        <div className="flex items-center bg-gray-100 rounded-lg px-3 py-3 my-2 text-sm space-x-3">
          <div className="h-4 w-px bg-gray-300"></div>
          {/* 利用回数の代わりに残り時間を表示（または併記） */}
          <div className="flex items-center text-gray-700">
            <ClockIcon className="w-4 h-4 mr-1 text-orange-500" />
            <span className="mr-1">
              残り時間: {formatSeconds(balance ?? 0)}
            </span>
            {/* 更新ボタン */}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 rounded-full hover:bg-gray-200 text-gray-500 ml-1"
              onClick={fetchProfile} // プロフィールを再取得する関数を呼ぶ
              title="残高を更新"
              disabled={profileLoading} // 読み込み中は無効化
            >
              <RefreshCwIcon
                className={`h-3 w-3 ${profileLoading ? "animate-spin" : ""}`}
              />
            </Button>
            {/* 購入ボタン */}
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 rounded-full bg-blue-100 hover:bg-blue-200 text-blue-600 ml-1"
              onClick={handleBuyCredits}
              title="時間を追加購入（30分 500円）"
            >
              <PlusIcon className="h-3 w-3" />
            </Button>
          </div>
          <div className="h-4 w-px bg-gray-300"></div>
          <div className="flex items-center text-gray-700">
            <RefreshCwIcon className="w-4 h-4 mr-1 text-green-500" />
            <span>利用回数: {profile.usage_count}回</span>
          </div>
        </div>
      ) : null}
      <div className="mb-4 space-x-2">
        {isRecording ? (
          <Button
            onClick={stopRecording}
            className="bg-red-500 hover:bg-red-600 text-white"
          >
            <SquareIcon className="w-4 h-4 mr-2" />
            停止
          </Button>
        ) : (
          <Button
            onClick={startRecording}
            className="bg-green-500 hover:bg-green-600 text-white"
            disabled={connectionStatus !== "connected"}
          >
            <MicIcon className="w-4 h-4 mr-2" />
            録音開始
          </Button>
        )}
        <Button
          onClick={generateMinutes}
          className="bg-blue-500 hover:bg-blue-600 text-white"
          disabled={!allTranscript}
        >
          議事録生成
        </Button>
        {minutes && (
          <Button
            onClick={downloadMinutes}
            className="bg-purple-500 hover:bg-purple-600 text-white"
          >
            <DownloadIcon className="w-4 h-4 mr-2" />
            議事録をダウンロード
          </Button>
        )}
      </div>
      <div className="my-2">
        {immediate && <p className="text-slate-500">リアルタイム文字起こし</p>}
        <h2 className="text-2xl">{immediate}</h2>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="col-span-1">
          <h2 className="text-xl font-semibold mb-2">全文</h2>
          <Textarea
            value={allTranscript || "ここに文字起こし結果が表示されます..."}
            readOnly
            className="w-full h-[300px] p-2 border rounded"
          />
        </div>
        <div className="col-span-1">
          <h2 className="text-xl font-semibold mb-2">生成された議事録</h2>
          <Textarea
            value={minutes}
            readOnly
            className="w-full h-[300px] p-2 border rounded"
          />
        </div>
      </div>
    </div>
  );
}
