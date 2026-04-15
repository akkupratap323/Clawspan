const { app, BrowserWindow, screen } = require('electron');

// Give V8's Oilpan heap enough room for the renderer process.
// Default reservation (~128 MB) is too small when a video is loaded.
app.commandLine.appendSwitch('js-flags', '--max-old-space-size=512');

// Disable hardware video decoding — the video is purely decorative and
// hardware decode pipelines consume the most Oilpan memory on macOS.
app.commandLine.appendSwitch('disable-accelerated-video-decode');

let win;

app.on('ready', () => {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;

  const hudW = 900;
  const hudH = 750;

  win = new BrowserWindow({
    width: hudW,
    height: hudH,
    x: width - hudW - 24,
    y: height - hudH - 24,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  win.loadFile('index.html');
  win.setIgnoreMouseEvents(true, { forward: true });
});

app.on('window-all-closed', () => app.quit());
