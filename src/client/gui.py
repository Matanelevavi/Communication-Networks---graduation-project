import tkinter as tk
from tkinter import messagebox, scrolledtext

def get_user_data_gui():
    user_data = {"action": None, "city": "", "profiles": [], "protocol": "RUDP"}
    def submit():
        action = action_var.get()
        city = city_entry.get().strip()

        raw_profiles = profiles_text.get("1.0", tk.END).strip().split('\n')
        for line in raw_profiles:
            if not line.strip(): continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                user_data["profiles"].append({
                    "name": parts[0], "gender": parts[1],
                    "age_category": parts[2], "notes": parts[3] if len(parts) > 3 else ""
                })

        if action == "FORECAST" and not city:
            messagebox.showwarning("Error", "Please enter a city.")
            return

        user_data["action"] = action
        user_data["city"] = city
        user_data["protocol"] = protocol_var.get()
        root.destroy()

    def on_closing():
        user_data["action"] = None
        root.destroy()

    root = tk.Tk()
    root.title("WeatherWear - Dashboard")
    root.geometry("550x550")
    root.configure(bg="#eef2f5")

    root.protocol("WM_DELETE_WINDOW", on_closing)

    header = tk.Frame(root, bg="#34495e", pady=15)
    header.pack(fill=tk.X)
    tk.Label(header, text="WeatherWear Command Center", font=("Helvetica", 16, "bold"), fg="white", bg="#34495e").pack()

    # 1. Action Card
    action_frame = tk.LabelFrame(root, text=" 1. Choose Action ", font=("Helvetica", 11, "bold"), bg="#ffffff", padx=10, pady=10)
    action_frame.pack(fill=tk.X, padx=20, pady=10)

    action_var = tk.StringVar(value="FORECAST")
    tk.Radiobutton(action_frame, text="Get AI Weather & Forecast", variable=action_var, value="FORECAST", bg="#ffffff", font=("Helvetica", 10)).pack(anchor=tk.W)
    tk.Radiobutton(action_frame, text="View History Archive", variable=action_var, value="FTP_LIST", bg="#ffffff", font=("Helvetica", 10)).pack(anchor=tk.W)

    # 2. Details Card
    details_frame = tk.LabelFrame(root, text=" 2. Details (For Forecast) ", font=("Helvetica", 11, "bold"), bg="#ffffff", padx=10, pady=10)
    details_frame.pack(fill=tk.X, padx=20, pady=10)

    tk.Label(details_frame, text="City:", font=("Helvetica", 10), bg="#ffffff").pack(anchor=tk.W)
    city_entry = tk.Entry(details_frame, font=("Helvetica", 10), width=30, bg="#f8f9fa", relief=tk.SOLID, borderwidth=1)
    city_entry.insert(0, "Ariel")
    city_entry.pack(anchor=tk.W, pady=(0, 10))

    tk.Label(details_frame, text="Family (Name, Gender, Age, Notes):", font=("Helvetica", 10), bg="#ffffff").pack(anchor=tk.W)
    profiles_text = tk.Text(details_frame, height=4, width=55, font=("Helvetica", 10), bg="#f8f9fa", relief=tk.SOLID, borderwidth=1)
    profiles_text.insert(tk.END, "Man, Male, Adult, \nWomen, Female, Adult, \nchild, Female, Baby, Daycare")
    profiles_text.pack(anchor=tk.W)

    # 3. Protocol Card
    proto_frame = tk.LabelFrame(root, text=" 3. Network Protocol ", font=("Helvetica", 11, "bold"), bg="#ffffff", padx=10, pady=10)
    proto_frame.pack(fill=tk.X, padx=20, pady=10)

    protocol_var = tk.StringVar(value="RUDP")
    tk.Radiobutton(proto_frame, text="RUDP", variable=protocol_var, value="RUDP", bg="#ffffff", font=("Helvetica", 10)).pack(anchor=tk.W)
    tk.Radiobutton(proto_frame, text="TCP", variable=protocol_var, value="TCP", bg="#ffffff", font=("Helvetica", 10)).pack(anchor=tk.W)

    tk.Button(root, text="Send Request", bg="#27ae60", fg="white", font=("Helvetica", 12, "bold"), relief=tk.FLAT, padx=20, pady=5, command=submit).pack(pady=15)
    root.mainloop()

    return (user_data["action"], user_data["city"], user_data["profiles"], user_data["protocol"]) if user_data["action"] else (None, None, None, None)

def show_ftp_list_gui(list_text):
    selected = {"filename": None}

    root = tk.Tk()
    root.title("FTP Archive, Select a File")
    root.geometry("400x400")
    root.configure(bg="#eef2f5")

    tk.Label(root, text="Double click a file to open", font=("Helvetica", 12, "bold"), bg="#eef2f5", pady=10).pack()

    listbox = tk.Listbox(root, font=("Helvetica", 12), selectbackground="#3498db", relief=tk.FLAT)
    listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=5)

    filenames = []
    for line in list_text.split('\n'):
        if line.startswith("- "):
            parts = line.split(' ')
            if len(parts) >= 2:
                fname = parts[1]
                filenames.append(fname)
                listbox.insert(tk.END, fname)

    if not filenames:
        listbox.insert(tk.END, "No files found in archive.")
        listbox.config(state=tk.DISABLED)

    def on_select(event=None):
        selection = listbox.curselection()
        if selection and filenames:
            selected["filename"] = filenames[selection[0]]
            root.destroy()

    listbox.bind('<Double-1>', on_select)
    tk.Button(root, text="Open Selected File", font=("Helvetica", 11, "bold"), bg="#2ecc71", fg="white", command=on_select, relief=tk.FLAT, padx=20).pack(pady=15)

    root.mainloop()
    return selected["filename"]

def show_result_gui(action, city, recommendation):
    root = tk.Tk()
    title_str = f"Plan for {city}" if action == "FORECAST" else "File Viewer"

    root.title(title_str)
    root.geometry("700x600")
    root.configure(bg="#eef2f5")

    header = tk.Frame(root, bg="#2980b9", pady=15)
    header.pack(fill=tk.X)

    tk.Label(header, text=title_str, font=("Helvetica", 20, "bold"), bg="#2980b9", fg="white").pack()

    text_area = scrolledtext.ScrolledText(root, wrap=tk.WORD, font=("Consolas", 11), bg="#ffffff", fg="#2c3e50", padx=15, pady=15, relief=tk.FLAT)
    text_area.insert(tk.END, recommendation)
    text_area.config(state=tk.DISABLED)
    text_area.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)

    tk.Button(root, text="Close", font=("Helvetica", 12, "bold"), bg="#e74c3c", fg="white", relief=tk.FLAT, padx=20, pady=8, command=root.destroy).pack(pady=(0, 20))
    root.mainloop()