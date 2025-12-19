"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MicIcon, SquareIcon, DownloadIcon } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import Image from "next/image"; // 追記

const SAMPLE_RATE = 16000;
const WS_URL = `ws://${process.env.NEXT_PUBLIC_HOST}/ws`;

export default function TranscriptionApp() {
  const [isRecording, setIsRecording] = useState(false);
  const [minutes, setMinutes] = useState<string>("");
  const websocketRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const [allTranscript, setAllTranscript] = useState<string>("");
  const [immediate, setImmediate] = useState<string>("");
  const { toast } = useToast();

  const connectWebSocket = useCallback(() => {
    if (websocketRef.current?.readyState === WebSocket.OPEN) return;

    websocketRef.current = new WebSocket(WS_URL);

    websocketRef.current.onopen = () => {};

    websocketRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

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
        console.error(error);
      }
    };

    websocketRef.current.onerror = () => {
      toast({
        title: "エラー",
        description: "WebSocket接続でエラーが発生しました。",
        variant: "destructive",
      });
    };

    websocketRef.current.onclose = () => {
      if (isRecording) {
        setTimeout(connectWebSocket, 3000);
      }
    };
  }, [isRecording, toast]);

  useEffect(() => {
    connectWebSocket();

    return () => {
      if (websocketRef.current) {
        websocketRef.current.close();
      }
    };
  }, [connectWebSocket]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioContextRef.current = new AudioContext({ sampleRate: SAMPLE_RATE });
      sourceRef.current =
        audioContextRef.current.createMediaStreamSource(stream);
      processorRef.current = audioContextRef.current.createScriptProcessor(
        1024,
        1,
        1
      );

      sourceRef.current.connect(processorRef.current);
      processorRef.current.connect(audioContextRef.current.destination);

      processorRef.current.onaudioprocess = (e) => {
        if (websocketRef.current?.readyState === WebSocket.OPEN) {
          const inputData = e.inputBuffer.getChannelData(0);
          const audioData = convertFloat32ToInt16(inputData);
          websocketRef.current.send(audioData);
        }
      };

      setIsRecording(true);
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
    if (audioContextRef.current) {
      sourceRef.current?.disconnect();
      processorRef.current?.disconnect();
      audioContextRef.current.close();
    }
    setIsRecording(false);
  };

  const generateMinutes = async () => {
    try {
      const response = await fetch(
        `http://${process.env.NEXT_PUBLIC_HOST}/generate_minutes`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            transcript: allTranscript,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || "Minutes generation failed");
      }

      const data = await response.json();
      setMinutes(data.minutes);
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
      <div className="flex border-b-2 border-yellow-400 mb-2">
        <Image
          className=""
          width={30}
          height={1}
          style={{ width: "auto", height: "100%" }}
          src="/logo.png"
          alt="logo"
        />
        <h1 className="text-2xl font-bold">リアルタイム議事録システム</h1>
      </div>
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
        <h2 className="text-2xl">{immediate.slice(-30)}</h2>
      </div>
      <div></div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="col-span-1">
          <div className="md:flex items-end mb-2">
            <h2 className="text-xl font-semibold mr-2">全文</h2>
          </div>
          <Textarea
            value={allTranscript}
            readOnly
            className="w-full h-[200px] p-2 border rounded"
          />
        </div>
        <div className="col-span-1">
          <h2 className="text-xl font-semibold mb-2">生成された議事録</h2>
          <Textarea
            value={minutes}
            readOnly
            className="w-full h-[200px] p-2 border rounded"
          />
        </div>
      </div>
    </div>
  );
}
