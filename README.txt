# Jelli Web - Phase 1 Setup

## Files in this folder
- `app.py` - Flask backend server
- `templates/index.html` - The web page
- `static/style.css` - Styling
- `static/app.js` - Frontend logic
- `static/logo.png` - The Jelli logo (you need to add this!)

## Setup steps

### 1. Install Flask
```
pip install flask
```

(You already have lyricsgenius, deep-translator, requests)

### 2. Add your logo
Copy your `logo.png` file into the `static/` folder.

### 3. Add your Genius API token
Open `app.py` and replace `PASTE_YOUR_TOKEN_HERE` with your token.

### 4. Run the server
```
cd Jelli-Web
python app.py
```

### 5. Open in browser
On your computer: http://localhost:5000

### 6. Open on your phone (same WiFi)
First, find your computer's IP address:
- **Windows:** In Command Prompt: `ipconfig` → look for "IPv4 Address"
- Example: 192.168.1.42

Then on your phone, open: `http://192.168.1.42:5000`
(replace with your actual IP)

⚠️ Both devices must be on the **same WiFi network**.
