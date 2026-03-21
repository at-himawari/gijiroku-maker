"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  MicIcon,
  SquareIcon,
  DownloadIcon,
  LogOutIcon,
  RefreshCwIcon,
  AlertCircleIcon,
  ClockIcon,
  PlusIcon,
  HistoryIcon,
  TrashIcon,
  CopyPlusIcon,
  LoaderCircleIcon,
  XIcon,
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

interface HistoryItem {
  id: string;
  date: string;
  transcript: string;
  minutes: string;
}

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
  const [isGenerating, setIsGenerating] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>("");
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const { toast } = useToast();
  const { logout, token, user } = useAuth();

  // ★課金情報取得用のフックを使用
  const {
    profile,
    fetchProfile,
    loading: profileLoading,
    error: profileError,
  } = useUserProfile();
  const historyListContent =
    history.length === 0 ? (
      <p className="text-gray-500 text-sm text-center py-10 md:py-4">
        履歴はありません。
      </p>
    ) : (
      <div className="space-y-3">
        {history.map((item) => (
          <div
            key={item.id}
            className="flex flex-col md:flex-row md:items-center justify-between p-4 border rounded-lg bg-white md:bg-gray-50 shadow-sm hover:border-gray-300 transition-colors"
          >
            <div className="mb-4 md:mb-0 md:mr-4 flex-1">
              <p className="font-semibold text-sm text-gray-700">{item.date}</p>
              <p className="text-xs text-gray-500 mt-1 line-clamp-2 md:w-96">
                {item.transcript || "文字起こしデータなし"}
              </p>
            </div>
            <div className="flex space-x-2 shrink-0">
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  loadFromHistory(item);
                  setIsHistoryModalOpen(false); // スマホ用：復元時にモーダルを閉じる
                }}
                className="bg-white"
              >
                復元して表示
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-red-500 hover:text-red-700 hover:bg-red-50 border-red-100"
                onClick={() => deleteHistoryItem(item.id)}
              >
                <TrashIcon className="w-4 h-4" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    );

  const updateHistory = useCallback(
    (sessionId: string, transcript: string, mins: string) => {
      if (!sessionId || (!transcript && !mins)) return;

      setHistory((prev) => {
        const existingIndex = prev.findIndex((h) => h.id === sessionId);
        let updatedHistory;

        if (existingIndex >= 0) {
          // すでに同じIDの履歴があれば、最新のテキストで上書き更新する（重複を防ぐ）
          updatedHistory = [...prev];
          updatedHistory[existingIndex] = {
            ...updatedHistory[existingIndex],
            transcript,
            minutes: mins,
            date: new Date().toLocaleString("ja-JP"), // 更新日時を最新にする
          };
        } else {
          // 新しいIDなら先頭に新規追加
          const newItem: HistoryItem = {
            id: sessionId,
            date: new Date().toLocaleString("ja-JP"),
            transcript,
            minutes: mins,
          };
          updatedHistory = [newItem, ...prev].slice(0, 20);
        }

        localStorage.setItem(
          "transcription_history",
          JSON.stringify(updatedHistory),
        );
        return updatedHistory;
      });
    },
    [],
  );

  // --- 変更: 初回読み込み時の復元処理 ---
  useEffect(() => {
    try {
      // 履歴一覧の復元
      const savedHistory = localStorage.getItem("transcription_history");
      if (savedHistory) setHistory(JSON.parse(savedHistory));

      // 作業中データの復元
      const savedTranscript = localStorage.getItem("current_transcript");
      const savedMinutes = localStorage.getItem("current_minutes");
      const savedSessionId = localStorage.getItem("current_session_id");

      if (savedTranscript) setAllTranscript(savedTranscript);
      if (savedMinutes) setMinutes(savedMinutes);

      // セッションIDの復元（なければ新規発行）
      if (savedSessionId) {
        setCurrentSessionId(savedSessionId);
      } else {
        const newId = Date.now().toString();
        setCurrentSessionId(newId);
        localStorage.setItem("current_session_id", newId);
      }
    } catch (e) {
      console.error("データの復元に失敗しました", e);
    }
  }, []);

  // --- 変更: テキストが更新されるたびに自動保存＆履歴も更新 ---
  useEffect(() => {
    if (allTranscript) {
      localStorage.setItem("current_transcript", allTranscript);
    } else {
      localStorage.removeItem("current_transcript");
    }

    if (minutes) {
      localStorage.setItem("current_minutes", minutes);
    } else {
      localStorage.removeItem("current_minutes");
    }

    // 文字起こしや議事録が変化したら、履歴一覧にも即座に上書き同期する
    if (currentSessionId && (allTranscript || minutes)) {
      updateHistory(currentSessionId, allTranscript, minutes);
    }
  }, [allTranscript, minutes, currentSessionId, updateHistory]);

  useEffect(() => {
    try {
      const savedHistory = localStorage.getItem("transcription_history");
      if (savedHistory) {
        setHistory(JSON.parse(savedHistory));
      }
    } catch (e) {
      console.error("履歴の読み込みに失敗しました", e);
    }
  }, []);

  // プロフィール読み込み時に残高をstateにセット
  useEffect(() => {
    if (profile) {
      const receivedBalance =
        profile.seconds_balance ?? (profile as any).secondsBalance;
      setBalance(receivedBalance);
    }
  }, [profile]);

  const clearCurrentSession = () => {
    if (
      window.confirm(
        "画面のデータをクリアして、新しい会議を始めますか？（履歴には残ります）",
      )
    ) {
      setAllTranscript("");
      setMinutes("");
      setImmediate("");

      // 新しい会議用のIDを発行
      const newId = Date.now().toString();
      setCurrentSessionId(newId);

      localStorage.removeItem("current_transcript");
      localStorage.removeItem("current_minutes");
      localStorage.setItem("current_session_id", newId);
    }
  };

  const loadFromHistory = (item: HistoryItem) => {
    if ((allTranscript || minutes) && currentSessionId !== item.id) {
      if (
        !window.confirm(
          "現在表示中のデータは上書きされます。履歴を読み込みますか？",
        )
      )
        return;
    }
    setAllTranscript(item.transcript);
    setMinutes(item.minutes);

    // 過去のIDを復元（これ以降の変更は過去の履歴を上書きするようになる）
    setCurrentSessionId(item.id);
    localStorage.setItem("current_session_id", item.id);

    toast({
      title: "履歴を読み込みました",
      description: `${item.date} の記録を表示しています`,
    });
  };

  const deleteHistoryItem = (id: string) => {
    const updatedHistory = history.filter((h) => h.id !== id);
    setHistory(updatedHistory);
    localStorage.setItem(
      "transcription_history",
      JSON.stringify(updatedHistory),
    );
    toast({ title: "履歴を削除しました" });
  };

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
        },
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
            }),
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

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;
      audioContextRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
      const blob = new Blob([WORKLET_CODE], { type: "application/javascript" });
      const workletUrl = URL.createObjectURL(blob);
      await audioContextRef.current.audioWorklet.addModule(workletUrl);
      sourceRef.current =
        audioContextRef.current.createMediaStreamSource(stream);

      const gainNode = audioContextRef.current.createGain();

      gainNode.gain.value = 1.5; // 音量を2.5倍に増幅

      const processor = new AudioWorkletNode(
        audioContextRef.current,
        "recorder-processor",
      );
      processorRef.current = processor;

      processor.port.onmessage = (e) => {
        if (globalWebSocket?.readyState === WebSocket.OPEN) {
          const audioData = convertFloat32ToInt16(e.data);
          globalWebSocket.send(audioData);
        }
      };

      sourceRef.current.connect(gainNode);
      gainNode.connect(processorRef.current);
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
    setIsGenerating(true);
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
    } finally {
      setIsGenerating(false);
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
      // -1.0 から 1.0 の範囲に値を制限（クリッピング）する
      const s = Math.max(-1, Math.min(1, buffer[i]));
      // 負の場合は 0x8000 (32768)、正の場合は 0x7fff (32767) を掛けるのがより正確です
      buf[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
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
      <div className="grid grid-cols-1 md:grid-cols-2 items-center border-b-2 border-yellow-400">
        <div className="flex items-center mb-4">
          <Image width={30} height={30} src="/logo.png" alt="logo" />
          <h1 className="text-2xl font-bold ml-2">
            リアルタイム議事録システム
          </h1>
        </div>
        <div className="flex justify-between items-center mb-2">
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
        <div className="flex items-center bg-gray-100 rounded-lg px-3 py-3 my-2 text-sm space-x-3 text-gray-400">
          <LoaderCircleIcon className="animate-spin" />
          インスタンスを起動中。しばらくお待ちください...
        </div>
      ) : profile ? (
        <>
          <div className="flex items-center bg-gray-100 rounded-lg px-3 py-3 my-2 text-sm space-x-3">
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
          <div className="mb-4 flex flex-wrap gap-3">
            <Button
              onClick={clearCurrentSession}
              variant="outline"
              className="border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700"
              disabled={!allTranscript && !minutes}
            >
              <CopyPlusIcon className="w-4 h-4 mr-2" />
              新しい会議
            </Button>
            <Button
              onClick={() => setIsHistoryModalOpen(true)}
              variant="outline"
              className="md:hidden border-gray-200 text-gray-700 hover:bg-gray-50"
            >
              <HistoryIcon className="w-4 h-4 mr-2" />
              履歴
            </Button>
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
              disabled={!allTranscript || isGenerating}
            >
              {isGenerating ? (
                <>
                  <RefreshCwIcon className="w-4 h-4 mr-2 animate-spin" />
                  生成中...
                </>
              ) : (
                <>
                  <RefreshCwIcon className="w-4 h-4 mr-2" />
                  議事録生成
                </>
              )}
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
        </>
      ) : null}

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
      <div className="hidden md:block mt-12 border-t pt-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center text-gray-800">
          <HistoryIcon className="w-5 h-5 mr-2" />
          過去の録音履歴
        </h2>
        {historyListContent}
      </div>

      {/* モバイル用の履歴モーダル */}
      {isHistoryModalOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-lg shadow-xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between p-4 border-b bg-gray-50">
              <h2 className="text-xl font-semibold flex items-center text-gray-800">
                <HistoryIcon className="w-5 h-5 mr-2" />
                過去の録音履歴
              </h2>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setIsHistoryModalOpen(false)}
                className="hover:bg-gray-200"
              >
                <XIcon className="w-5 h-5" />
              </Button>
            </div>
            <div className="p-4 overflow-y-auto flex-1">
              {historyListContent}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
