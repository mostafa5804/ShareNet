from __future__ import annotations

import ipaddress
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import ClassVar

import customtkinter as ctk
from PIL import Image

from . import __version__
from .config import load_config, recommend_pc_ip, save_config, validate_config
from .credentials import delete_password, get_password, set_password
from .diagnostics import export_sanitized
from .engine import bundle_root, detect_windows_network, run_engine
from .privilege import ElevationError, relaunch_as_admin_if_needed
from .service import disable, dry_run, enable, make_driver

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

BG = "#F4F7FB"
CARD = "#FFFFFF"
TEXT = "#14213D"
MUTED = "#64748B"
BLUE = "#176BFF"
TEAL = "#11A7A2"
RED = "#E5484D"
BORDER = "#DCE4EF"


class ShareNetApp(ctk.CTk):
    DRIVER_LABELS: ClassVar[dict[str, str]] = {
        "Archer C80 — خودکار": "tp_link_archer_c80",
        "سایر مودم‌ها — تنظیم دستی": "manual",
    }

    def __init__(self):
        super().__init__(fg_color=BG)
        self.title(f"ShareNet Gateway v{__version__}")
        self.geometry("1180x820")
        self.minsize(1040, 720)
        self.cfg = load_config()
        self.events: queue.Queue = queue.Queue()
        self.action_buttons: list[ctk.CTkButton] = []
        self._set_window_icon()
        self._build_ui()
        self.after(120, self._poll_events)

    def _asset(self, name: str) -> Path:
        return bundle_root() / "assets" / name

    def _set_window_icon(self) -> None:
        try:
            self.iconbitmap(self._asset("sharenet.ico"))
        except (tk.TclError, OSError):
            pass

    def _build_ui(self) -> None:
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=26, pady=22)
        self._build_header(shell)

        body = ctk.CTkFrame(shell, fg_color="transparent")
        body.pack(fill="both", expand=True, pady=(18, 0))
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.left = ctk.CTkScrollableFrame(
            body, fg_color="transparent", corner_radius=0, scrollbar_button_color="#C7D3E3"
        )
        self.left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self.right = ctk.CTkFrame(
            body, fg_color=CARD, corner_radius=18, border_width=1, border_color=BORDER
        )
        self.right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        self._init_vars()
        self._build_mode_card()
        self._build_settings_card()
        self._build_steps()
        self._build_actions()
        self._build_log()
        self._update_driver_ui()

        saved = get_password(self.vars["router_url"].get(), self.vars["username"].get())
        if saved:
            self.vars["password"].set(saved)

    def _build_header(self, parent) -> None:
        header = ctk.CTkFrame(parent, fg_color="transparent")
        header.pack(fill="x")
        try:
            image = ctk.CTkImage(Image.open(self._asset("sharenet-logo.png")), size=(58, 58))
            ctk.CTkLabel(header, image=image, text="").pack(side="left", padx=(0, 14))
        except OSError:
            pass
        title = ctk.CTkFrame(header, fg_color="transparent")
        title.pack(side="left")
        ctk.CTkLabel(title, text="ShareNet", font=("Segoe UI", 26, "bold"), text_color=TEXT).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            title,
            text="اشتراک SOCKS5 کامپیوتر با دستگاه‌های شبکه",
            font=("Segoe UI", 12),
            text_color=MUTED,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text=f"نسخه {__version__}  •  Windows 10/11 x64",
            fg_color="#E8F0FF",
            text_color=BLUE,
            corner_radius=12,
            padx=14,
            pady=7,
            font=("Segoe UI", 11, "bold"),
        ).pack(side="right")

    def _init_vars(self) -> None:
        current = next(
            (
                label
                for label, key in self.DRIVER_LABELS.items()
                if key == self.cfg["router"].get("driver")
            ),
            "Archer C80 — خودکار",
        )
        self.vars = {
            "driver_label": tk.StringVar(value=current),
            "router_url": tk.StringVar(value=self.cfg["router"]["base_url"]),
            "username": tk.StringVar(value=self.cfg["router"].get("username", "admin")),
            "password": tk.StringVar(),
            "router_ip": tk.StringVar(value=self.cfg["network"]["router_ip"]),
            "lan_cidr": tk.StringVar(value=self.cfg["network"]["lan_cidr"]),
            "pc_ip": tk.StringVar(value=self.cfg["network"]["pc_ip"]),
            "socks": tk.StringVar(
                value=f"{self.cfg['proxy']['address']}:{self.cfg['proxy']['port']}"
            ),
            "remember": tk.BooleanVar(value=True),
        }

    def _card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(
            parent, fg_color=CARD, corner_radius=18, border_width=1, border_color=BORDER
        )
        card.pack(fill="x", pady=(0, 12))
        return card

    def _build_mode_card(self) -> None:
        card = self._card(self.left)
        ctk.CTkLabel(
            card, text="روش تنظیم مودم", font=("Segoe UI", 15, "bold"), text_color=TEXT
        ).pack(anchor="e", padx=18, pady=(14, 8))
        self.driver_box = ctk.CTkOptionMenu(
            card,
            variable=self.vars["driver_label"],
            values=list(self.DRIVER_LABELS),
            command=lambda _: self._update_driver_ui(),
            height=38,
            fg_color="#EDF3FF",
            button_color=BLUE,
            button_hover_color="#105AD9",
            text_color=TEXT,
            dropdown_font=("Segoe UI", 11),
            font=("Segoe UI", 11, "bold"),
        )
        self.driver_box.pack(fill="x", padx=18, pady=(0, 8))
        self.mode_hint = ctk.CTkLabel(
            card, text="", wraplength=650, justify="right", font=("Segoe UI", 11), text_color=MUTED
        )
        self.mode_hint.pack(fill="x", padx=18, pady=(0, 14))

    def _field(self, parent, row: int, label: str, key: str, secret: bool = False):
        ctk.CTkLabel(parent, text=label, text_color=TEXT, font=("Segoe UI", 11)).grid(
            row=row, column=1, sticky="e", padx=(10, 18), pady=6
        )
        entry = ctk.CTkEntry(
            parent,
            textvariable=self.vars[key],
            show="•" if secret else "",
            height=36,
            corner_radius=9,
            border_color=BORDER,
            fg_color="#FBFCFE",
            font=("Segoe UI", 11),
        )
        entry.grid(row=row, column=0, sticky="ew", padx=(18, 0), pady=6)
        return entry

    def _build_settings_card(self) -> None:
        card = self._card(self.left)
        card.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            card, text="تنظیمات اتصال", font=("Segoe UI", 15, "bold"), text_color=TEXT
        ).grid(row=0, column=0, columnspan=2, sticky="e", padx=18, pady=(14, 8))
        self.router_entries = [
            self._field(card, 1, "آدرس پنل مودم", "router_url"),
            self._field(card, 2, "نام کاربری", "username"),
            self._field(card, 3, "رمز ورود مودم", "password", True),
        ]
        self.remember = ctk.CTkCheckBox(
            card,
            text="ذخیره امن رمز در Windows Credential Manager",
            variable=self.vars["remember"],
            text_color=MUTED,
            font=("Segoe UI", 10),
            fg_color=TEAL,
            hover_color="#0D8D89",
        )
        self.remember.grid(row=4, column=0, sticky="w", padx=18, pady=(2, 8))
        self._field(card, 5, "IP مودم / Gateway", "router_ip")
        self._field(card, 6, "محدوده LAN", "lan_cidr")
        self._field(card, 7, "IP ثابت این کامپیوتر", "pc_ip")
        self._field(card, 8, "آدرس SOCKS5", "socks")

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(row=9, column=0, columnspan=2, sticky="ew", padx=18, pady=(8, 16))
        ctk.CTkButton(
            row,
            text="تشخیص خودکار شبکه",
            command=self.detect,
            fg_color="#E9F0FA",
            hover_color="#DCE7F5",
            text_color=TEXT,
            height=37,
        ).pack(side="right", expand=True, fill="x", padx=(6, 0))
        ctk.CTkButton(
            row,
            text="ذخیره تنظیمات",
            command=self.save_safe,
            fg_color=BLUE,
            hover_color="#105AD9",
            height=37,
        ).pack(side="right", expand=True, fill="x", padx=(0, 6))

    def _build_steps(self) -> None:
        card = self._card(self.left)
        ctk.CTkLabel(
            card, text="آماده‌سازی امن", font=("Segoe UI", 15, "bold"), text_color=TEXT
        ).pack(anchor="e", padx=18, pady=(14, 8))
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=18, pady=(0, 16))
        for number, text, command in (
            ("۱", "تشخیص شبکه", self.detect),
            ("۲", "تست مودم", self.test_router),
            ("۳", "Dry Run", self.preview),
        ):
            button = ctk.CTkButton(
                row,
                text=f"{number}   {text}",
                command=command,
                fg_color="#EDF3FF",
                hover_color="#DCE8FF",
                text_color=BLUE,
                border_width=1,
                border_color="#C9D9FA",
                height=40,
                font=("Segoe UI", 11, "bold"),
            )
            button.pack(side="right", expand=True, fill="x", padx=4)
            self.action_buttons.append(button)
            if number == "۲":
                self.test_router_button = button

    def _build_actions(self) -> None:
        row = ctk.CTkFrame(self.left, fg_color="transparent")
        row.pack(fill="x", pady=(0, 12))
        for text, command, color, hover in (
            ("فعال‌سازی اشتراک", self.turn_on, BLUE, "#105AD9"),
            ("غیرفعال‌سازی و بازگردانی", self.turn_off, RED, "#C93D42"),
        ):
            button = ctk.CTkButton(
                row,
                text=text,
                command=command,
                fg_color=color,
                hover_color=hover,
                height=48,
                corner_radius=12,
                font=("Segoe UI", 13, "bold"),
            )
            button.pack(side="right", expand=True, fill="x", padx=5)
            self.action_buttons.append(button)

    def _build_log(self) -> None:
        ctk.CTkLabel(
            self.right, text="راهنمای همین حالت", font=("Segoe UI", 16, "bold"), text_color=TEXT
        ).pack(anchor="e", padx=20, pady=(18, 4))
        self.guide = ctk.CTkTextbox(
            self.right,
            height=255,
            fg_color="#F8FAFD",
            border_width=0,
            corner_radius=12,
            font=("Segoe UI", 11),
            text_color=TEXT,
            wrap="word",
        )
        self.guide.pack(fill="x", padx=16, pady=(6, 10))
        ctk.CTkButton(
            self.right,
            text="مشاهده مودم‌های سازگار",
            command=self.show_compatibility,
            fg_color="transparent",
            hover_color="#EDF3FF",
            text_color=BLUE,
            border_width=1,
            border_color="#BCD0FA",
            height=36,
        ).pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkLabel(
            self.right, text="وضعیت و گزارش", font=("Segoe UI", 15, "bold"), text_color=TEXT
        ).pack(anchor="e", padx=20)
        self.output = ctk.CTkTextbox(
            self.right,
            fg_color="#101827",
            text_color="#D7E2F1",
            corner_radius=12,
            font=("Consolas", 10),
            wrap="word",
        )
        self.output.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        footer = ctk.CTkFrame(self.right, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 16))
        ctk.CTkButton(
            footer,
            text="وضعیت",
            command=self.status,
            width=90,
            fg_color="#E9F0FA",
            hover_color="#DCE7F5",
            text_color=TEXT,
        ).pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            footer,
            text="گزارش پاک‌سازی‌شده",
            command=self.diagnostics,
            width=150,
            fg_color="#E9F0FA",
            hover_color="#DCE7F5",
            text_color=TEXT,
        ).pack(side="right")
        self.write("آماده — ابتدا تشخیص شبکه، سپس تست مودم و Dry Run را اجرا کنید.")

    def write(self, text: str) -> None:
        self.output.insert("end", text.rstrip() + "\n\n")
        self.output.see("end")

    def _manual_mode(self) -> bool:
        return self.DRIVER_LABELS[self.vars["driver_label"].get()] == "manual"

    def _update_driver_ui(self) -> None:
        manual = self._manual_mode()
        for entry in self.router_entries:
            entry.configure(state="disabled" if manual else "normal")
        self.remember.configure(state="disabled" if manual else "normal")
        self.test_router_button.configure(text="۲   راهنمای مودم" if manual else "۲   تست مودم")
        self.mode_hint.configure(
            text=(
                "بدون ورود رمز در ShareNet؛ پس از فعال‌سازی، Gateway و DNS نمایش‌داده‌شده "
                "را خودتان در صفحه DHCP Server مودم وارد می‌کنید."
                if manual
                else "تنظیم خودکار و تست‌شده برای TP-Link Archer C80 با پنل انگلیسی."
            )
        )
        guide = (
            "حالت دستی — برای بیشتر مودم‌ها\n\n"
            "۱) تشخیص شبکه را اجرا کنید.\n"
            "۲) Dry Run را بررسی کنید.\n"
            "۳) از تنظیمات فعلی DHCP مودم عکس بگیرید.\n"
            "۴) فعال‌سازی را بزنید. برنامه Default Gateway و Primary DNS را می‌دهد.\n"
            "۵) در پنل مودم، بخش LAN / DHCP Server، همان دو مقدار را وارد و Save کنید.\n"
            "۶) Wi‑Fi دستگاه مقصد را خاموش/روشن کنید.\n\n"
            "رمز مودم را فقط در صفحه رسمی خود مودم وارد کنید؛ ShareNet در حالت دستی "
            "آن را نمی‌گیرد. برای بازگردانی، ابتدا مقادیر قبلی مودم را برگردانید."
            if manual
            else "حالت خودکار — Archer C80\n\n"
            "۱) آدرس پنل و رمز مودم را وارد کنید.\n"
            "۲) تشخیص شبکه را اجرا کنید.\n"
            "۳) تست مودم باید Gateway/DNS فعلی را بخواند.\n"
            "۴) Dry Run را کنترل و سپس فعال‌سازی را بزنید.\n\n"
            "رمز داخل config.json نوشته نمی‌شود و فقط با انتخاب شما در Windows "
            "Credential Manager ذخیره خواهد شد."
        )
        self.guide.configure(state="normal")
        self.guide.delete("1.0", "end")
        self.guide.insert("1.0", guide)
        self.guide.configure(state="disabled")

    def show_compatibility(self) -> None:
        win = ctk.CTkToplevel(self)
        win.title("مودم‌های سازگار")
        win.geometry("650x540")
        win.transient(self)
        win.grab_set()
        ctk.CTkLabel(
            win, text="سازگاری مودم‌ها", font=("Segoe UI", 20, "bold"), text_color=TEXT
        ).pack(anchor="e", padx=24, pady=(22, 6))
        text = (
            "خودکار و تست‌شده\n• TP-Link Archer C80 — پنل انگلیسی\n\n"
            "تنظیم دستی مستندشده\n• MikroTik RouterOS\n• OpenWrt\n\n"
            "احتمالاً قابل استفاده در حالت دستی (نیازمند بررسی firmware)\n"
            "• TP-Link TL-WR940N v6 / TL-WR902AC v3 / TL-WR841N v14 / VX230v\n"
            "• بسیاری از مدل‌های ASUS، D-Link، Tenda، Huawei و ZTE\n\n"
            "شرط سازگاری حالت دستی\n"
            "مودم باید در DHCP Server اجازه تعیین Default Gateway و DNS را بدهد. "
            "مودم قفل‌شده ISP یا مدلی که Gateway سفارشی ندارد مناسب نیست. مدل و نسخه "
            "firmware مهم‌تر از نام برند است."
        )
        box = ctk.CTkTextbox(win, fg_color="#F8FAFD", font=("Segoe UI", 12), text_color=TEXT)
        box.pack(fill="both", expand=True, padx=24, pady=14)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkButton(win, text="بستن", command=win.destroy, fg_color=BLUE).pack(pady=(0, 20))

    def _current_config(self) -> dict:
        cfg = load_config()
        host, port = self.vars["socks"].get().strip().rsplit(":", 1)
        cfg["router"].update(
            base_url=self.vars["router_url"].get().strip(),
            username=self.vars["username"].get().strip(),
            driver=self.DRIVER_LABELS[self.vars["driver_label"].get()],
        )
        cfg["network"].update(
            router_ip=self.vars["router_ip"].get().strip(),
            lan_cidr=self.vars["lan_cidr"].get().strip(),
            pc_ip=self.vars["pc_ip"].get().strip(),
        )
        cfg["proxy"].update(address=host, port=int(port))
        validate_config(cfg)
        return cfg

    def _password(self) -> str:
        value = self.vars["password"].get()
        if not value:
            raise ValueError("رمز مودم وارد نشده است.")
        return value

    def save(self, quiet: bool = False) -> dict:
        cfg = self._current_config()
        save_config(cfg)
        if not self._manual_mode():
            if self.vars["remember"].get() and self.vars["password"].get():
                set_password(cfg["router"]["base_url"], cfg["router"]["username"], self._password())
            elif not self.vars["remember"].get():
                delete_password(cfg["router"]["base_url"], cfg["router"]["username"])
        self.cfg = cfg
        if not quiet:
            self.write("✓ تنظیمات غیرحساس ذخیره شد؛ رمز داخل فایل config نوشته نشد.")
        return cfg

    def save_safe(self) -> None:
        try:
            self.save()
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports validation errors
            messagebox.showerror("تنظیمات نامعتبر", str(exc))

    def _prepare(self, require_password: bool = False):
        try:
            cfg = self.save(quiet=True)
            return cfg, self._password() if require_password else None
        except Exception as exc:  # noqa: BLE001 - GUI boundary reports validation errors
            messagebox.showerror("تنظیمات نامعتبر", str(exc))
            return None

    def _busy(self, state: bool) -> None:
        for button in self.action_buttons:
            button.configure(state="disabled" if state else "normal")
        self.configure(cursor="wait" if state else "")

    def _run_async(self, label: str, function) -> None:
        self._busy(True)
        self.write(f"… {label}")

        def worker():
            try:
                self.events.put(("ok", str(function())))
            except Exception as exc:  # noqa: BLE001 - worker errors must reach the GUI
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def detect(self) -> None:
        def action():
            data = detect_windows_network()
            self.events.put(("detected", data))
            return f"شبکه شناسایی شد: {data.get('adapter')}"

        self._run_async("در حال تشخیص شبکه", action)

    def _poll_events(self) -> None:
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "detected":
                    gateway = data.get("gateway")
                    prefix = int(data.get("prefix", 24))
                    if gateway:
                        self.vars["router_ip"].set(gateway)
                        self.vars["router_url"].set(f"http://{gateway}")
                        network = ipaddress.ip_network(f"{gateway}/{prefix}", strict=False)
                        self.vars["lan_cidr"].set(str(network))
                        self.vars["pc_ip"].set(recommend_pc_ip(str(network), gateway))
                    continue
                self._busy(False)
                self.write(("✓ " if kind == "ok" else "✗ ") + str(data))
                if kind == "error":
                    messagebox.showerror("ShareNet", str(data))
                elif "بخش Windows فعال شد" in str(data):
                    messagebox.showinfo(
                        "تنظیم دستی مودم", str(data).split("بخش Windows فعال شد.", 1)[-1].strip()
                    )
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    def test_router(self) -> None:
        if self._manual_mode():
            messagebox.showinfo(
                "تنظیم دستی مودم",
                "در این حالت رمز را فقط داخل پنل مودم وارد کنید. ابتدا Dry Run و سپس "
                "فعال‌سازی را اجرا کنید؛ ShareNet مقادیر Gateway و DNS را نمایش می‌دهد.",
            )
            return
        prepared = self._prepare(require_password=True)
        if not prepared:
            return
        cfg, password = prepared

        def action():
            value = make_driver(cfg, password).read_dhcp()
            return (
                "اتصال مودم موفق بود.\n"
                f"Gateway فعلی: {value.default_gateway or '(خالی)'}\n"
                f"DNS فعلی: {value.primary_dns or '(خالی)'}\n"
                f"DHCP Pool: {value.pool_start} تا {value.pool_end}"
            )

        self._run_async("تست read-only مودم", action)

    def preview(self) -> None:
        prepared = self._prepare(require_password=not self._manual_mode())
        if prepared:
            cfg, password = prepared
            self._run_async("در حال آماده‌سازی Dry Run", lambda: dry_run(cfg, password).format_fa())

    def turn_on(self) -> None:
        prepared = self._prepare(require_password=not self._manual_mode())
        if not prepared:
            return
        cfg, password = prepared
        text = (
            "بخش Windows فعال می‌شود و سپس باید DHCP مودم را طبق مقادیر نمایش‌داده‌شده "
            "دستی تغییر دهید. Dry Run را بررسی کرده‌اید؟"
            if self._manual_mode()
            else "IP، forwarding و DHCP مودم تغییر می‌کند. Dry Run را بررسی کرده‌اید؟"
        )
        if messagebox.askyesno("تأیید فعال‌سازی", text):
            self._run_async("در حال فعال‌سازی و بررسی نتیجه", lambda: enable(cfg, password))

    def turn_off(self) -> None:
        if self._manual_mode() and not messagebox.askyesno(
            "بازگردانی دستی مودم",
            "ابتدا Gateway و DNS قبلی را در DHCP Server مودم برگردانید. انجام شد؟",
        ):
            return
        prepared = self._prepare(require_password=not self._manual_mode())
        if not prepared:
            return
        cfg, password = prepared
        if messagebox.askyesno("بازگردانی شبکه", "شبکه و Windows به وضعیت قبلی برگردد؟"):
            self._run_async("در حال بازگردانی", lambda: disable(cfg, password))

    def status(self) -> None:
        prepared = self._prepare()
        if prepared:
            cfg, _ = prepared
            self._run_async("بررسی وضعیت", lambda: run_engine("status", cfg))

    def diagnostics(self) -> None:
        filename = filedialog.asksaveasfilename(
            title="ذخیره گزارش پاک‌سازی‌شده",
            defaultextension=".zip",
            filetypes=[("ZIP", "*.zip")],
            initialfile="ShareNet-diagnostics-sanitized.zip",
        )
        if filename:
            path = export_sanitized(Path(filename))
            self.write(f"✓ گزارش پاک‌سازی‌شده ساخته شد: {path}")


def main() -> int:
    try:
        if relaunch_as_admin_if_needed():
            return 0
    except ElevationError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("دسترسی Administrator", str(exc))
        root.destroy()
        return 1
    app = ShareNetApp()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
