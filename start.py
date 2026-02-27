import subprocess
import webbrowser
import time

print("Starting BotD SaaS...")

# Install dependencies
subprocess.run(["pip", "install", "-r", "requirements.txt"])

# Start API server
subprocess.Popen(["python", "api.py"])

# Wait and open dashboard
time.sleep(3)
webbrowser.open("dashboard.html")

print("BotD SaaS is running!")
print("API: http://localhost:5000")
print("Dashboard: Open in browser")
