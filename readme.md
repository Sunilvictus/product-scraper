
# 🛒 Product Catalog Scraper (Playwright + Python)

This project is part of the **IdenHQ Automation Challenge**.  
It demonstrates **web automation, session handling, smart waits, pagination handling, and structured data export** using [Playwright](https://playwright.dev/python/) in Python.

---

## 🚀 Features
- ✅ Uses Playwright with Chromium  
- ✅ Smart session management (saves/reuses session to avoid repeated logins)  
- ✅ Handles nested hover menus (`Data Tools → Inventory Management → Product Catalog`)  
- ✅ Extracts product table data (including **pagination & lazy-loading**)  
- ✅ Exports structured JSON (`products.json`)  
- ✅ Environment-variable based credential management (`.env`)  
- ✅ Clean, well-documented, and robust error handling  

---

## 📂 Project Structure
```

project-root/
│── product_scraper.py   # Main scraper script
│── .env                 
│── requirements.txt     
│── .gitignore              
│── products.json        
│── README.md           

````

---

## ⚡ Installation & Usage

### 1. Clone the Repository
```bash
git clone https://github.com/SunilSuthar7/product-scraper.git
cd product-scraper
````

### 2. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure Credentials

Create a `.env` file in the project root:

```env
USERNAME=your_username
PASSWORD=your_password
```

### 4. Run the Script

```bash
python product_scraper.py
```

### 5. Check the Output

The scraped data will be saved as:

```
products.json
```

---

## 🛡 Security

* Credentials are **never hardcoded** in the script.
* `.env` file is **excluded via `.gitignore`** to protect sensitive data.
* Session storage is reused securely to reduce unnecessary logins.

---




## ✨ Why This Project Stands Out

* Follows **best practices** in automation
* Production-ready structure with modular, documented code
* Shows skills in **web scraping, automation, and Python development**
* Recruiter-friendly: can be run easily with clear instructions

---

## 👨‍💻 Author

**Sunil Suthar G**
  [GitHub](https://github.com/SunilSuthar7)

---


