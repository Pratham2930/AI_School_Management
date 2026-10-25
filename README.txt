# 🏫 AI School Management System


An AI-powered School Management System built with Python to simplify school administration, student management, academic operations, and data-driven insights.

## 📌 About the Project

The AI School Management System is a Python-based application designed to support school administration through digital management tools and AI/ML-related functionality.

The project brings together school management workflows, student-related machine learning components, analytics, and administrative features in one application.

## ✨ Features

- 👨‍🎓 Student Management
- 👩‍🏫 Teacher Management
- 📚 Academic Management
- 📊 Analytics and Reporting
- 🤖 AI/ML Student Analysis Components
- 📝 Student Leave Management
- 💰 Fee Management and Verification
- 🔐 Role-Based Permissions
- 📈 Power BI Reporting Support

*Feature availability depends on the application's current configuration.*

## 🛠️ Technologies Used

- Python
- HTML
- CSS
- JavaScript
- Machine Learning
- Flask / Python Web Framework
- Power BI Reporting
- Git and GitHub

## 📂 Project Structure

```text
AI_School_Management/
│
├── ai/                  # AI and ML components
├── agents/              # School agents and permissions
├── ml/                  # Machine learning utilities
├── templates/           # HTML templates
├── tests/               # Automated tests
├── kafka_pipeline/      # Event processing components
│
├── app.py               # Main application
├── wsgi.py              # WSGI entry point
├── requirements.txt     # Python dependencies
├── docker-compose.yml   # Docker configuration
├── DEPLOYMENT.md        # Deployment documentation
├── POWER_BI_REPORTING.md
└── README.md
```

## ⚙️ Installation and Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Pratham2930/AI_School_Management.git
```

### 2. Navigate to the Project

```bash
cd AI_School_Management
```

### 3. Create a Virtual Environment

```bash
python -m venv .venv
```

### 4. Activate the Virtual Environment

For Windows:

```powershell
.venv\Scripts\Activate.ps1
```

For Linux or macOS:

```bash
source .venv/bin/activate
```

### 5. Install Dependencies

```bash
pip install -r requirements.txt
```

### 6. Run the Application

```bash
python app.py
```

Check the application's terminal output for the local URL and open it in your browser.

For additional deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md).

## 🧪 Testing

Run the project's automated tests using:

```bash
python -m pytest
```

Install pytest first if it is not included in the project's dependencies.

## 📊 Documentation

- [Deployment Guide](DEPLOYMENT.md)
- [Project Audit](PROJECT_AUDIT.md)
- [Power BI Reporting](POWER_BI_REPORTING.md)

## 🔒 Security

- Do not commit API keys, passwords, or secret credentials.
- Do not upload real student personal information.
- Keep environment variables and private configuration files out of version control.
- Use appropriate access controls when deploying the application.

## 🚀 Future Improvements

- Advanced student performance prediction
- AI-powered academic insights
- Improved analytics dashboard
- Automated attendance analysis
- Enhanced security and access management





## 👨‍💻 Author

**Pratham Raval**

GitHub: [@Pratham2930](https://github.com/Pratham2930)

## 📄 License

No license has been specified yet.
