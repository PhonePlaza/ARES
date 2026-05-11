# ARES - Android Pentesting Agent

ARES เป็นโปรเจคสำหรับช่วยทำ Android penetration testing ผ่านหน้าเว็บ โดยรวม `AI`, `Frida`, `ADB` และระบบ report ไว้ใน workflow เดียว

ตัวระบบออกแบบมาเพื่อช่วยให้การวิเคราะห์แอป Android เร็วขึ้น ตั้งแต่เลือก APK, ให้ AI ช่วยสร้างหรือปรับ Frida script, รันกับแอปจริง, ดู log แบบ realtime, ไปจนถึงสรุปผลออกเป็น report

## Main Features

- วิเคราะห์ APK และข้อมูลเบื้องต้นของแอป
- ให้ AI ช่วย generate, refine และ heal Frida script
- inject script เข้า target app ผ่าน Frida
- ดู Frida logs และ `adb logcat` แบบ realtime
- screen mirror device บนหน้าเว็บ พร้อม tap/swipe input
- สร้าง report และ export PDF ได้

## Project Structure

- `main.py` - FastAPI backend
- `app/` - Next.js frontend
- `routers/` - API routes และ WebSocket endpoints
- `services/` - business logic เช่น AI, Frida, analysis
- `reports/` - เก็บ report ที่สร้างแล้ว

## Basic Flow

1. ต่อ Android device หรือ emulator และเปิด `frida-server`
2. รัน backend (`python main.py`)
3. รัน frontend (`npm run dev`)
4. เลือก APK หรือ target app ที่ต้องการทดสอบ
5. ใช้ AI ช่วยสร้างหรือปรับ Frida script
6. รัน script, ดู logs และตรวจ behavior แบบ realtime
7. สร้าง report เพื่อสรุปผลการทดสอบ

## Run

Backend:

```bash
python main.py
```

Frontend:

```bash
npm run dev
```

เปิดใช้งานที่:

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
