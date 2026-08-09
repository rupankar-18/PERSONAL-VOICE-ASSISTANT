const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow = null;
let pythonProcess = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    frame: false,
    transparent: true,
    alwaysOnTop: false,
    resizable: true,
    hasShadow: true,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: true,
      contextIsolation: false,
      webSecurity: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function getPythonExecutable() {
  const fs = require('fs');
  const venvPython = path.join(__dirname, 'venv', 'Scripts', 'python.exe');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return 'python';
}

function launchPythonBackend() {
  const pythonExecutable = getPythonExecutable();
  const agentScript = path.join(__dirname, 'agent.py');

  console.log('[Electron Main] Spawning Python Assistant Backend process automatically...');
  pythonProcess = spawn(pythonExecutable, [agentScript, 'console'], {
    cwd: __dirname,
    stdio: 'inherit',
  });

  pythonProcess.on('exit', (code, signal) => {
    console.log(`[Electron Main] Python Assistant Backend process exited with code ${code}, signal ${signal}`);
  });
}

function runFaceAuthentication(callback) {
  const pythonExecutable = getPythonExecutable();
  const authScript = path.join(__dirname, 'face_authenticator.py');

  console.log('============================================================');
  console.log('      SECURITY LOCK - ADMIN FACE AUTHENTICATION ON APP OPEN');
  console.log('============================================================');
  console.log('[Electron Main] Accessing camera for security face scan on application launch...');

  const authProcess = spawn(pythonExecutable, [authScript], {
    cwd: __dirname,
    stdio: 'inherit',
  });

  authProcess.on('exit', (code) => {
    if (code === 0) {
      console.log('============================================================');
      console.log(' [SUCCESS] Admin identity confirmed! Launching 3D Assistant App...');
      console.log('============================================================');
      callback(true);
    } else {
      console.log('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!');
      console.log(' [SECURITY ALERT] Face not matched or unauthorized user!');
      console.log(' Access Denied. Desktop Application will NOT open.');
      console.log('!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!');
      callback(false);
    }
  });
}

app.whenReady().then(() => {
  runFaceAuthentication((success) => {
    if (success) {
      launchPythonBackend();
      createWindow();
    } else {
      app.quit();
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
});
