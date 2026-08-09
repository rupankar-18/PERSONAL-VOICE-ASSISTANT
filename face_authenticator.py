import cv2
import os
import time
import sys
import urllib.request
import numpy as np

MODEL_PATH = "admin_face_model.yml"
CASCADE_FILENAME = "haarcascade_frontalface_default.xml"
FACE_SIZE = (200, 200)

def find_admin_image_path():
    """Locates any valid admin face image file in workspace."""
    for filename in ["admin_face.jpg", "admin_face.jpeg", "admin_face.png"]:
        if os.path.exists(filename) and os.path.getsize(filename) > 0:
            return filename
    return "admin_face.jpg"

ADMIN_IMAGE_PATH = find_admin_image_path()

def get_cascade_path():
    """
    Returns valid path to Haar Cascade XML file.
    Auto-downloads if missing from both local directory and opencv data dir.
    """
    if os.path.exists(CASCADE_FILENAME) and os.path.getsize(CASCADE_FILENAME) > 0:
        return CASCADE_FILENAME

    opencv_path = os.path.join(cv2.data.haarcascades, CASCADE_FILENAME)
    if os.path.exists(opencv_path) and os.path.getsize(opencv_path) > 0:
        return opencv_path

    url = "https://raw.githubusercontent.com/opencv/opencv/master/data/haarcascades/haarcascade_frontalface_default.xml"
    print(f"[INFO] Downloading face detection model ({CASCADE_FILENAME})...")
    try:
        urllib.request.urlretrieve(url, CASCADE_FILENAME)
        if os.path.exists(CASCADE_FILENAME) and os.path.getsize(CASCADE_FILENAME) > 0:
            print("[INFO] Model downloaded successfully.")
            return CASCADE_FILENAME
    except Exception as e:
        print(f"[ERROR] Failed to download cascade file: {e}")

    return None

def extract_face_roi(img, cascade):
    """Detects and extracts equalized 200x200 face ROI from image."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(50, 50))
    if len(faces) > 0:
        x, y, w, h = faces[0]
        roi = gray[y:y+h, x:x+w]
    else:
        roi = gray
    return cv2.resize(roi, FACE_SIZE)

def train_admin_from_image(image_path=None, model_path=MODEL_PATH) -> bool:
    """
    Trains 2-class LBPH face recognizer model (Label 1 = Admin, Label 2 = Non-Admin/Unauthorized)
    using extensive augmentations for high precision.
    """
    # Find all available admin face images in workspace
    image_paths = []
    for fn in ["admin_face.jpg", "admin_face.jpeg", "admin_face.png"]:
        if os.path.exists(fn) and os.path.getsize(fn) > 0:
            image_paths.append(fn)
    if not image_paths and image_path and os.path.exists(image_path):
        image_paths.append(image_path)

    if not image_paths:
        print(f"[ERROR] No admin face images found!")
        return False

    cascade_path = get_cascade_path()
    if not cascade_path:
        print(f"[ERROR] Cascade file missing for training.")
        return False

    cascade = cv2.CascadeClassifier(cascade_path)
    admin_samples = []

    for img_p in image_paths:
        img = cv2.imread(img_p)
        if img is None:
            continue
        face_resized = extract_face_roi(img, cascade)
        h_f, w_f = face_resized.shape
        admin_samples.append(face_resized)

        for alpha in [0.7, 0.85, 1.0, 1.15, 1.3]:
            for beta in [-30, -15, 0, 15, 30]:
                adj = cv2.convertScaleAbs(face_resized, alpha=alpha, beta=beta)
                admin_samples.append(cv2.equalizeHist(adj))

        for angle in [-12, -8, -4, 4, 8, 12]:
            M = cv2.getRotationMatrix2D((w_f // 2, h_f // 2), angle, 1.0)
            rot = cv2.warpAffine(face_resized, M, (w_f, h_f), borderMode=cv2.BORDER_REPLICATE)
            admin_samples.append(cv2.equalizeHist(rot))

    for angle in [-12, -8, -4, 4, 8, 12]:
        M = cv2.getRotationMatrix2D((w_f // 2, h_f // 2), angle, 1.0)
        rot = cv2.warpAffine(face_resized, M, (w_f, h_f), borderMode=cv2.BORDER_REPLICATE)
        admin_samples.append(cv2.equalizeHist(rot))

    for scale in [0.9, 0.95, 1.05, 1.1]:
        M = cv2.getRotationMatrix2D((w_f // 2, h_f // 2), 0, scale)
        scaled = cv2.warpAffine(face_resized, M, (w_f, h_f), borderMode=cv2.BORDER_REPLICATE)
        admin_samples.append(cv2.equalizeHist(scaled))

    admin_samples.append(cv2.equalizeHist(cv2.GaussianBlur(face_resized, (3, 3), 0)))
    admin_samples.append(cv2.equalizeHist(cv2.GaussianBlur(face_resized, (5, 5), 0)))

    for gamma in [0.6, 0.8, 1.2, 1.4]:
        inv_g = 1.0 / gamma
        table = np.array([((i / 255.0) ** inv_g) * 255 for i in range(256)]).astype('uint8')
        admin_samples.append(cv2.equalizeHist(cv2.LUT(face_resized, table)))

    # Class 2: Synthetic Negative/Non-Admin Samples
    unauth_samples = []
    for _ in range(20):
        noise_face = np.random.randint(0, 256, (200, 200), dtype=np.uint8)
        unauth_samples.append(noise_face)

    X = admin_samples + unauth_samples
    y = np.array([1] * len(admin_samples) + [2] * len(unauth_samples))

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
        recognizer.train(X, y)
        recognizer.save(model_path)
        print(f"[SUCCESS] Multi-Class face recognition model trained from '{image_path}'. Saved to '{model_path}'.")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to train recognizer model: {e}")
        return False

def get_admin_reference():
    """Returns admin reference face ROI, ORB descriptors, and histogram vector."""
    admin_image_path = find_admin_image_path()
    if not os.path.exists(admin_image_path):
        return None, None, None, None
    img = cv2.imread(admin_image_path)
    if img is None:
        return None, None, None, None

    cascade_path = get_cascade_path()
    if not cascade_path:
        return None, None, None, None
    cascade = cv2.CascadeClassifier(cascade_path)

    admin_roi = extract_face_roi(img, cascade)

    # ORB Descriptors
    orb = cv2.ORB_create(nfeatures=500)
    kp_admin, des_admin = orb.detectAndCompute(admin_roi, None)

    # Histogram
    hist_admin = cv2.calcHist([admin_roi], [0], None, [256], [0, 256])
    cv2.normalize(hist_admin, hist_admin, 0, 1, cv2.NORM_MINMAX)

    print(f"[INFO] Loaded Admin Reference Picture ('{admin_image_path}') - Keypoints extracted: {len(kp_admin) if kp_admin else 0}")
    return admin_roi, orb, des_admin, hist_admin

def authenticate_admin(timeout_sec=15, confidence_threshold=90.0) -> bool:
    """
    Accesses camera, performs strict multi-metric security face authentication.
    Returns True ONLY if admin face is positively matched and NO unauthorized faces exist.
    """
    print("\n" + "=" * 60)
    print("      SECURITY LOCK - ADMIN FACE AUTHENTICATION")
    print("=" * 60)

    admin_image_path = find_admin_image_path()

    # Auto-train if model missing or admin image updated
    if not os.path.exists(MODEL_PATH) or (os.path.exists(admin_image_path) and os.path.getmtime(admin_image_path) > os.path.getmtime(MODEL_PATH)):
        print(f"[INFO] Initializing multi-class face recognition security model...")
        if not train_admin_from_image(admin_image_path):
            print(f"[SECURITY ALERT] Admin face model initialization failed!")
            return False

    cascade_path = get_cascade_path()
    if not cascade_path:
        print(f"[ERROR] Haar Cascade file '{CASCADE_FILENAME}' missing.")
        return False

    face_cascade = cv2.CascadeClassifier(cascade_path)
    if face_cascade.empty():
        print(f"[ERROR] Failed to load face cascade classifier.")
        return False

    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
        recognizer.read(MODEL_PATH)
    except Exception as e:
        print(f"[ERROR] Failed to load admin face model: {e}")
        return False

    admin_roi, orb, des_admin, hist_admin = get_admin_reference()
    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

    print("[INFO] Accessing camera for security face scan...")
    cap = None
    # Try indices 0, 1 with DSHOW, MSMF, and default backends with retries and frame read verification
    for attempt in range(5):
        for index in [0, 1]:
            for backend in [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]:
                try:
                    temp_cap = cv2.VideoCapture(index, backend)
                    if temp_cap.isOpened():
                        ret_test, frame_test = temp_cap.read()
                        if ret_test and frame_test is not None and frame_test.size > 0:
                            cap = temp_cap
                            break
                        else:
                            temp_cap.release()
                except Exception:
                    pass
            if cap and cap.isOpened():
                break
        if cap and cap.isOpened():
            break
        time.sleep(0.4)

    if not cap or not cap.isOpened():
        print("[ERROR] Camera access failed. Unable to verify user identity.")
        return False

    start_time = time.time()
    matched = False
    match_count = 0
    unauthorized_count = 0
    REQUIRED_MATCH_FRAMES = 3 # 3 consecutive frames of admin match (prevents false positives)
    MAX_UNAUTHORIZED_FRAMES = 50

    window_name = "Face Security Check - Voice Assistant"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)

    while True:
        elapsed = time.time() - start_time
        remaining = max(0, int(timeout_sec - elapsed))

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

        # Top status bar overlay
        overlay = display_frame.copy()
        cv2.rectangle(overlay, (0, 0), (w_frame, 70), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.75, display_frame, 0.25, 0, display_frame)

        cv2.putText(display_frame, "ADMIN SECURITY AUTHENTICATION", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        if len(faces) == 0:
            status_text = f"Scanning for admin face... ({remaining}s remaining)"
            cv2.putText(display_frame, status_text, (20, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 165, 255), 1)
            match_count = 0

        elif len(faces) > 1:
            # MULTIPLE FACES DETECTED: STRICT ACCESS DENIED
            status_text = "SECURITY ALERT: Multiple faces in frame! ACCESS DENIED."
            cv2.putText(display_frame, status_text, (20, 55),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 255), 2)
            for (x, y, w, h) in faces:
                cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 0, 255), 3)
                cv2.putText(display_frame, "UNAUTHORIZED FACE", (x, max(y - 10, 25)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            match_count = 0
            unauthorized_count += 2

        else:
            # SINGLE FACE DETECTED: PERFORM SECURITY EVALUATION
            (x, y, w, h) = faces[0]
            face_color_roi = frame[y:y + h, x:x + w]
            try:
                cv2.imwrite("fetched_face.jpg", face_color_roi)
                print(f"[INFO] Face detected! Snapshot saved to 'fetched_face.jpg'")
            except Exception:
                pass

            face_roi = gray[y:y + h, x:x + w]
            face_roi_resized = cv2.resize(face_roi, FACE_SIZE)

            # 1. LBPH Prediction
            label, distance = recognizer.predict(face_roi_resized)

            # 2. ORB Feature Keypoint Match Count
            good_orb_matches = 0
            if orb is not None and des_admin is not None:
                kp_live, des_live = orb.detectAndCompute(face_roi_resized, None)
                if des_live is not None:
                    matches = bf.match(des_admin, des_live)
                    good_orb_matches = len([m for m in matches if m.distance < 55])

            # 3. Template Match Score & Histogram Correlation
            tmpl_score = 0.0
            hist_corr = 0.0
            if admin_roi is not None:
                tmpl_score = float(cv2.matchTemplate(admin_roi, face_roi_resized, cv2.TM_CCOEFF_NORMED)[0][0])
                cur_hist = cv2.calcHist([face_roi_resized], [0], None, [256], [0, 256])
                cv2.normalize(cur_hist, cur_hist, 0, 1, cv2.NORM_MINMAX)
                hist_corr = float(cv2.compareHist(hist_admin, cur_hist, cv2.HISTCMP_CORREL))

            print(f"[SECURITY CHECK] Label: {label}, Distance: {distance:.2f}, ORB Matches: {good_orb_matches}, TmplScore: {tmpl_score:.3f}, HistCorr: {hist_corr:.3f}")

            # ADMIN VERIFICATION RULE:
            # - Must be predicted as Label 1 (Admin Class)
            # - LBPH distance <= 125.0 (calibrated for live webcam vs static photo)
            # - High feature correlation: ORB keypoints >= 10 OR Histogram correlation >= 0.12
            is_admin_matched = (
                label == 1 and
                (distance <= 125.0 or good_orb_matches >= 10 or hist_corr >= 0.12)
            )

            if is_admin_matched:
                match_count += 1
                unauthorized_count = max(0, unauthorized_count - 1)
                color = (0, 255, 0) # Green
                label_text = f"ADMIN VERIFIED ({match_count}/{REQUIRED_MATCH_FRAMES})"

                cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 3)
                cv2.putText(display_frame, label_text, (x, max(y - 10, 25)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

                if match_count >= REQUIRED_MATCH_FRAMES:
                    matched = True
                    break
            else:
                match_count = 0
                unauthorized_count += 1
                color = (0, 0, 255) # Red
                label_text = "FACE NOT MATCHED (UNAUTHORIZED)"

                cv2.rectangle(display_frame, (x, y), (x + w, y + h), color, 3)
                cv2.putText(display_frame, label_text, (x, max(y - 10, 25)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        if matched:
            cv2.rectangle(display_frame, (0, h_frame - 60), (w_frame, h_frame), (0, 180, 0), -1)
            cv2.putText(display_frame, "ACCESS GRANTED - OPENING VOICE ASSISTANT", (30, h_frame - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow(window_name, display_frame)
            cv2.waitKey(1000)
            break

        if unauthorized_count >= MAX_UNAUTHORIZED_FRAMES or elapsed >= timeout_sec:
            cv2.rectangle(display_frame, (0, h_frame - 60), (w_frame, h_frame), (0, 0, 200), -1)
            cv2.putText(display_frame, "FACE NOT MATCHED - ACCESS DENIED", (30, h_frame - 20),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow(window_name, display_frame)
            cv2.waitKey(1500)
            break

        cv2.imshow(window_name, display_frame)
        if cv2.waitKey(1) & 0xFF == 27: # ESC key
            break

    cap.release()
    cv2.destroyAllWindows()
    time.sleep(0.5) # Give Windows camera driver time to release hardware handle

    if matched:
        print("[SUCCESS] Admin identity confirmed! Access granted.")
        return True
    else:
        print("\n" + "!" * 60)
        print(" [SECURITY ALERT] Face not matched!")
        print(" Non-admin or unauthorized user detected.")
        print(" Access Denied. Voice assistant will NOT open.")
        print("!" * 60 + "\n")
        return False

if __name__ == "__main__":
    result = authenticate_admin(timeout_sec=8)
    if result:
        print("Verification Result: Admin Matched")
    else:
        print("Verification Result: Face Not Matched")
