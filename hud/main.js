const { app, BrowserWindow, screen } = require('electron');

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
