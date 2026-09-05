# 佐倉みどりのリファレンス音声

`sakura_midori.wav` は Irodori-TTS のゼロショット音声クローン用リファレンス。
**ここが正**で、Irodori-TTS-Server 側の `voices/sakura_midori.wav` はここへの
シンボリックリンク（`characters/sakura_midori.yaml` と同じ方式）。

## 出どころ（Build Log #013）

実在の人物の声はクローンしていない。**Irodori-TTS 自身に caption と seed を与えて
生成した音声**を、そのままリファレンスとして固定したもの。

| 項目 | 値 |
|---|---|
| モデル | `Aratako/Irodori-TTS-v4-Small` |
| caption | `ボーイッシュな女性の声。さっぱりとした話し方。` |
| seed | `1006` |
| 生成時のセリフ | `ドクター、今日もSO-101の実験、見てるよ。黄色いブロック、ちょっとずれてるね。次はうまくいくと思う。` |
| 形式 | WAV / 16bit / mono / 48kHz / 約10.8秒 |

同じ caption と seed を `POST /v1/audio/speech` に渡せば、この声はいつでも再現できる。

```bash
curl -X POST http://localhost:8088/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"irodori-tts","input":"（任意のセリフ）","voice":"none","response_format":"wav",
       "caption":"ボーイッシュな女性の声。さっぱりとした話し方。","seed":1006}' \
  --output out.wav
```

## なぜリファレンスを固定するのか

`voice: 'none'` は声を毎回サンプリングするため、サーバー既定の分割合成
（`IRODORI_DEFAULT_CHUNKING_ENABLED=true` / `CHUNK_MIN_CHARS=80`）と重なって、
**文の区切りごとに別人の声になる**。リファレンスを固定するとチャンクもターンも
同じ声になる。
