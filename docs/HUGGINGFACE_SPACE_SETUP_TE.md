# Hugging Face Space ఏర్పాటు — తెలుగు గైడ్

ఈ గైడ్ Macherla Guru AI Video Worker కోసం. ఇది YouTube Manager నుంచి పూర్తిగా వేరు.

## 1. Space సృష్టించండి

1. మొబైల్ బ్రౌజర్‌లో https://huggingface.co/new-space తెరవండి.
2. Hugging Face ఖాతాలో sign in అవ్వండి.
3. Space name: `macherla-guru-ai-video-worker` (పేరు అందుబాటులో లేకపోతే మీకు నచ్చిన ప్రత్యేక పేరు).
4. SDK: **Gradio** ఎంచుకోండి.
5. Visibility: మొదట **Private** ఎంచుకోవచ్చు.
6. Create Space నొక్కండి.

## 2. కోడ్ ఫైళ్లు పెట్టండి

GitHub Actions లోని `macherla-guru-hf-space` artifact ZIPను డౌన్‌లోడ్ చేసి extract చేయాలి. అందులోని `app.py`, అన్ని `.py` modules, `requirements.txt`, `README.md` ఫైళ్లను Space repositoryకి upload చేయాలి.

## 3. Gemini Secret

Spaceలో Settings → Variables and secrets → New secret:
- Name: `GEMINI_API_KEY`
- Value: మీ Gemini API key

API keyని GitHubలో లేదా chatలో paste చేయవద్దు.

## 4. GPU గురించి ముఖ్యమైన పరిమితి

- ZeroGPU అనేది Gradio Spaces కోసం తాత్కాలిక GPU మాత్రమే.
- Free personal accountకు అర్హత ఉంటే రోజుకు 5 GPU నిమిషాలు.
- `xlarge` GPU quotaను రెండింతలు ఖర్చు చేస్తుంది.
- మన పూర్తి multi-scene Wan2.2 rendererకు persistent CUDA GPU అవసరం. ZeroGPUతో పూర్తి కథ render అవుతుందని హామీ లేదు.
- Paid GPU, credits, billing ఏవీ యజమాని స్పష్టమైన అనుమతి లేకుండా ప్రారంభించకూడదు.

## 5. ప్రస్తుత స్థితి

Space source code, unit tests సిద్ధంగా ఉన్నాయి. Space సృష్టించడం, నిజమైన Wan2.2 model weights పెట్టడం, GPU inference పరీక్ష, Telugu lip-sync ఇంకా పూర్తి కాలేదు. CI PASS అనేది కోడ్ పరీక్ష మాత్రమే; నిజమైన వీడియో render అయ్యిందని కాదు.

YouTube Manager యొక్క `app.py` ఫైల్ ఈ ప్రాజెక్ట్‌లో మార్చకూడదు.
