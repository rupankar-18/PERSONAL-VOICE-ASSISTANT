import cv2
import os
import time
import urllib.request
import numpy as np
from face_authenticator import train_admin_from_image, MODEL_PATH, ADMIN_IMAGE_PATH, FACE_SIZE, get_cascade_path, CASCADE_FILENAME

TOTAL_SAMPLES_NEEDED = 40

def capture_and_train_admin():
    print("=" * 60)
    print("      ADMIN FACE ENROLLMENT - VOICE ASSISTANT")
    print("=" * 60)

    # Check if admin_face.jpg already exists
    if os.path.exists(ADMIN_IMAGE_PATH):
        print(f"[INFO] Found existing admin face image: '{ADMIN_IMAGE_PATH}'")
        print("[INFO] Training face recognition model from admin photo...")
        if train_admin_from_image(ADMIN_IMAGE_PATH, MODEL_PATH):
            print(f"[SUCCESS] Admin model trained and saved to '{MODEL_PATH}'.")
            return True

    print("[INFO] Starting camera... Please look into the camera.")
    print("[TIP] Keep neutral expression, slightly turn head left/right for better model training.")

    cascade_path = get_cascade_path()
    if not cascade_path:
        print(f"[ERROR] Haar Cascade file '{CASCADE_FILENAME}' could not be located or downloaded.")
        return False

    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        print(f"[ERROR] Failed to load cascade classifier from: {cascade_path}")
        return False

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not access the camera. Please check your camera connection.")
        return False

    face_samples = []
    ids = []
    count = 0
    recording = False
    last_sample_time = time.time()

    print("[INFO] Press 's' to start recording face samples, or press 'q' / ESC to quit.")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[ERROR] Failed to read frame from camera.")
            break

        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(100, 100)
        )

        display_frame = frame.copy()
        h_frame, w_frame = display_frame.shape[:2]

        overlay = display_frame.copy()
        cv2.rectangle(overlay, (0, 0), (w_frame, 80), (30, 30, 30), -1)
        cv2.addWeighted(overlay, 0.7, display_frame, 0.3, 0, display_frame)

        if len(faces) == 0:
            status_text = "No Face Detected - Position yourself in front of camera"
            status_color = (0, 165, 255)
        elif len(faces) > 1:
            status_text = "Multiple faces detected - Ensure ONLY admin is in frame"
            status_color = (0, 0, 255)
        else:
            status_text = "Face Detected! Recording admin features..."
            status_color = (0, 255, 0)

        cv2.putText(display_frame, "ADMIN FACE REGISTRATION", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.putText(display_frame, status_text, (20, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 1)

        if len(faces) == 1:
            (x, y, w, h) = faces[0]
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            face_roi = gray[y:y + h, x:x + w]
            face_roi_resized = cv2.resize(face_roi, FACE_SIZE)

            if not recording and (time.time() - last_sample_time > 1.2):
                recording = True

            if recording and count < TOTAL_SAMPLES_NEEDED:
                if time.time() - last_sample_time > 0.08:
                    count += 1
                    face_samples.append(face_roi_resized)
                    ids.append(1) # Admin ID = 1
                    last_sample_time = time.time()

                    if count == 1:
                        cv2.imwrite(ADMIN_IMAGE_PATH, frame[y:y+h, x:x+w])

            progress = int((count / TOTAL_SAMPLES_NEEDED) * (w_frame - 40))
            cv2.rectangle(display_frame, (20, h_frame - 40), (w_frame - 20, h_frame - 20), (50, 50, 50), -1)
            cv2.rectangle(display_frame, (20, h_frame - 40), (20 + progress, h_frame - 20), (0, 255, 0), -1)
            cv2.putText(display_frame, f"Recording Admin Face: {count}/{TOTAL_SAMPLES_NEEDED}", (30, h_frame - 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

        cv2.imshow("Admin Face Capture", display_frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('s'):
            recording = True
        elif key == ord('q') or key == 27:
            print("[INFO] Capture cancelled by user.")
            cap.release()
            cv2.destroyAllWindows()
            return False

        if count >= TOTAL_SAMPLES_NEEDED:
            break

    cap.release()
    cv2.destroyAllWindows()

    if len(face_samples) < TOTAL_SAMPLES_NEEDED:
        print("[ERROR] Insufficient face samples collected.")
        return False

    print(f"[INFO] Training high-precision face recognition model with {len(face_samples)} samples...")
    recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
    recognizer.train(face_samples, np.array(ids))
    recognizer.save(MODEL_PATH)

    print(f"[SUCCESS] Admin face trained & saved to '{MODEL_PATH}'.")
    return True

if __name__ == "__main__":
    success = capture_and_train_admin()
    if success:
        print("\nNow run 'python agent.py'. Only your face will unlock the assistant.")
    else:
        print("\nAdmin face capture failed or was cancelled.")

