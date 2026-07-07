import customtkinter as ctk
from tkinter import filedialog

from app.downloaders import download_images


class TechTubeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("TechTube AI v1.0")
        self.geometry("850x700")

        self.save_folder = ""
        self._build_ui()

    def _build_ui(self):
        title = ctk.CTkLabel(self, text="TechTube AI", font=("Arial", 30, "bold"))
        title.pack(pady=20)

        instruction = ctk.CTkLabel(self, text="Paste one keyword per line")
        instruction.pack()

        self.textbox = ctk.CTkTextbox(self, width=700, height=250)
        self.textbox.pack(pady=10)

        frame = ctk.CTkFrame(self)
        frame.pack(pady=10)

        label = ctk.CTkLabel(frame, text="Images per keyword:")
        label.pack(side="left", padx=10)

        self.count_entry = ctk.CTkEntry(frame, width=60)
        self.count_entry.insert(0, "5")
        self.count_entry.pack(side="left")

        browse_button = ctk.CTkButton(self, text="Choose Save Folder", command=self.browse_folder)
        browse_button.pack(pady=10)

        self.folder_label = ctk.CTkLabel(self, text="No folder selected")
        self.folder_label.pack()

        self.progress = ctk.CTkProgressBar(self, width=500)
        self.progress.pack(pady=20)
        self.progress.set(0)

        download_button = ctk.CTkButton(self, text="Download Images", command=self.download_images, height=40)
        download_button.pack(pady=20)

        self.status_label = ctk.CTkLabel(self, text="Status: Waiting...")
        self.status_label.pack()

    def browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.save_folder = folder
            self.folder_label.configure(text=folder)

    def _update_status(self, message: str) -> None:
        self.status_label.configure(text=message)

    def download_images(self):
        keywords = self.textbox.get("1.0", "end").strip().split("\n")
        keywords = [k.strip() for k in keywords if k.strip()]

        try:
            images_per_keyword = int(self.count_entry.get())
        except ValueError:
            images_per_keyword = 5

        self.status_label.configure(text=f"Ready to download {len(keywords)} keywords")
        self.progress.set(0)
        download_images(
            keywords=keywords,
            save_folder=self.save_folder,
            images_per_keyword=images_per_keyword,
            status_callback=self._update_status,
            progress_callback=self.progress.set,
        )

    def run(self):
        self.mainloop()


def run_app():
    app = TechTubeApp()
    app.run()
