

import argparse
import json
import logging
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime, timedelta

TASKS_FILE = "tasks.json"
LOG_FILE = "file_scheduler.log"
OPERATIONS = ("copy", "move", "delete", "archive")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DATETIME_FMT = "%Y-%m-%d %H:%M"


# --------------------------------------------------------------------------
# Logger
# --------------------------------------------------------------------------
class Logger:
    

    def __init__(self, log_file=LOG_FILE):
        self.log_file = log_file
        self._logger = logging.getLogger("file_scheduler")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not self._logger.handlers:
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                                  "%Y-%m-%d %H:%M:%S"))
            self._logger.addHandler(handler)

    def success(self, task, message=""):
        self._logger.info("Задача #%s [%s] %s -> УСПЕХ %s",
                          task.task_id, task.operation, task.source, message)

    def failure(self, task, error):
        self._logger.error("Задача #%s [%s] %s -> ОШИБКА: %s",
                           task.task_id, task.operation, task.source, error)

    def info(self, message):
        self._logger.info(message)

    def read(self):
        if not os.path.exists(self.log_file):
            return ""
        with open(self.log_file, encoding="utf-8") as f:
            return f.read()


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------
class Task:
    

    def __init__(self, task_id, operation, source, destination=None,
                 schedule="daily:00:00", last_run=None, created=None):
        self.task_id = task_id
        self.operation = operation
        self.source = source
        self.destination = destination
        self.schedule = schedule
        self.last_run = last_run  # datetime | None
        self.created = created or datetime.now()  # точка отсчёта до первого запуска

    # --- расписание -------------------------------------------------------
    def next_run(self, now=None):
        
        now = now or datetime.now()
        kind, _, rest = self.schedule.partition(":")
        ref = self.last_run or self.created  # отсчёт от последнего запуска или от создания

        if kind == "once":
            moment = datetime.strptime(rest, DATETIME_FMT)
            return None if self.last_run else moment

        if kind == "interval":
            minutes = int(rest)
            return ref + timedelta(minutes=minutes)

        if kind == "hourly":
            start = ref.replace(minute=0, second=0, microsecond=0)
            return start + timedelta(hours=1)

        if kind == "daily":
            hh, mm = map(int, rest.split(":"))
            candidate = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if candidate <= ref:
                candidate += timedelta(days=1)
            return candidate

        if kind == "weekly":
            day, hh, mm = rest.split(":")
            target = WEEKDAYS.index(day)
            hh, mm = int(hh), int(mm)
            candidate = ref.replace(hour=hh, minute=mm, second=0, microsecond=0)
            candidate += timedelta(days=(target - candidate.weekday()) % 7)
            if candidate <= ref:
                candidate += timedelta(days=7)
            return candidate

        raise ValueError(f"Неизвестный формат расписания: {self.schedule}")

    def is_due(self, now=None):
        now = now or datetime.now()
        nxt = self.next_run(now)
        return nxt is not None and nxt <= now

    # --- сериализация -----------------------------------------------------
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "operation": self.operation,
            "source": self.source,
            "destination": self.destination,
            "schedule": self.schedule,
            "last_run": self.last_run.strftime("%Y-%m-%d %H:%M:%S") if self.last_run else None,
            "created": self.created.strftime("%Y-%m-%d %H:%M:%S"),
        }

    @classmethod
    def from_dict(cls, data):
        fmt = "%Y-%m-%d %H:%M:%S"
        last, created = data.get("last_run"), data.get("created")
        return cls(data["task_id"], data["operation"], data["source"],
                   data.get("destination"), data["schedule"],
                   datetime.strptime(last, fmt) if last else None,
                   datetime.strptime(created, fmt) if created else None)

    def __repr__(self):
        nxt = self.next_run()
        nxt_s = nxt.strftime(DATETIME_FMT) if nxt else "-"
        return (f"#{self.task_id:<3} {self.operation:<8} {self.source:<25} "
                f"-> {str(self.destination or '-'):<20} {self.schedule:<18} "
                f"след. запуск: {nxt_s}")


# --------------------------------------------------------------------------
# FileOperations
# --------------------------------------------------------------------------
class FileOperations:
    

    @staticmethod
    def copy(source, destination):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        if os.path.isdir(source):
            target = os.path.join(destination, os.path.basename(os.path.normpath(source)))
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            os.makedirs(destination, exist_ok=True)
            target = shutil.copy2(source, destination)
        return f"скопировано в {target}"

    @staticmethod
    def move(source, destination):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        os.makedirs(destination, exist_ok=True)
        target = shutil.move(source, destination)
        return f"перемещено в {target}"

    @staticmethod
    def delete(source):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        if os.path.isdir(source):
            shutil.rmtree(source)
        else:
            os.remove(source)
        return "удалено"

    @staticmethod
    def archive(source, destination):
        if not os.path.exists(source):
            raise FileNotFoundError(f"Источник не найден: {source}")
        os.makedirs(destination, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = os.path.basename(os.path.normpath(source))
        zip_path = os.path.join(destination, f"{name}_{stamp}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            if os.path.isdir(source):
                for root, _, files in os.walk(source):
                    for fn in files:
                        full = os.path.join(root, fn)
                        z.write(full, os.path.relpath(full, os.path.dirname(os.path.normpath(source))))
            else:
                z.write(source, name)
        return f"архив создан: {zip_path}"


# --------------------------------------------------------------------------
# Scheduler
# --------------------------------------------------------------------------
class Scheduler:
    """Хранит задачи (в JSON), проверяет расписание и запускает задачи."""

    def __init__(self, tasks_file=TASKS_FILE, logger=None):
        self.tasks_file = tasks_file
        self.logger = logger or Logger()
        self.tasks = []
        self.load()

    # --- хранение ---------------------------------------------------------
    def load(self):
        if os.path.exists(self.tasks_file):
            with open(self.tasks_file, encoding="utf-8") as f:
                self.tasks = [Task.from_dict(d) for d in json.load(f)]

    def save(self):
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump([t.to_dict() for t in self.tasks], f, ensure_ascii=False, indent=2)

    def _next_id(self):
        return max((t.task_id for t in self.tasks), default=0) + 1

    # --- валидация --------------------------------------------------------
    @staticmethod
    def validate_schedule(schedule):
        kind, _, rest = schedule.partition(":")
        try:
            if kind == "once":
                datetime.strptime(rest, DATETIME_FMT)
            elif kind == "interval":
                if int(rest) <= 0:
                    raise ValueError
            elif kind == "hourly":
                pass
            elif kind == "daily":
                datetime.strptime(rest, "%H:%M")
            elif kind == "weekly":
                day, _, t = rest.partition(":")
                if day not in WEEKDAYS:
                    raise ValueError
                datetime.strptime(t, "%H:%M")
            else:
                raise ValueError
        except ValueError:
            raise ValueError(
                "Неверное расписание. Допустимо: once:YYYY-MM-DD HH:MM, interval:N, "
                "hourly, daily:HH:MM, weekly:mon..sun:HH:MM")

    # --- управление задачами ---------------------------------------------
    def add_task(self, operation, source, destination, schedule):
        if operation not in OPERATIONS:
            raise ValueError(f"Операция должна быть одной из: {', '.join(OPERATIONS)}")
        if operation != "delete" and not destination:
            raise ValueError(f"Для операции {operation} нужен параметр --destination")
        self.validate_schedule(schedule)
        task = Task(self._next_id(), operation, source, destination, schedule)
        self.tasks.append(task)
        self.save()
        self.logger.info(f"Добавлена задача #{task.task_id} ({operation}, {schedule})")
        return task

    def remove_task(self, task_id):
        for t in self.tasks:
            if t.task_id == task_id:
                self.tasks.remove(t)
                self.save()
                self.logger.info(f"Удалена задача #{task_id}")
                return True
        return False

    def get_task(self, task_id):
        return next((t for t in self.tasks if t.task_id == task_id), None)

    def run_task(self, task):
        try:
            if task.operation == "copy":
                msg = FileOperations.copy(task.source, task.destination)
            elif task.operation == "move":
                msg = FileOperations.move(task.source, task.destination)
            elif task.operation == "delete":
                msg = FileOperations.delete(task.source)
            elif task.operation == "archive":
                msg = FileOperations.archive(task.source, task.destination)
            else:
                raise ValueError(f"Неизвестная операция: {task.operation}")
            self.logger.success(task, f"({msg})")
            status = "УСПЕХ"
        except Exception as e:  # ошибка одной задачи не должна остановить шедулер
            self.logger.failure(task, e)
            status = f"ОШИБКА: {e}"
        task.last_run = datetime.now()
        self.save()
        return status

    def run_pending(self, now=None):
        for task in list(self.tasks):
            if task.is_due(now):
                print(f"[{datetime.now():%H:%M:%S}] Запуск задачи #{task.task_id}: {self.run_task(task)}")
                if task.schedule.startswith("once:"):
                    self.remove_task(task.task_id)  # разовая задача выполнена

    def start(self, poll_seconds=1):
        print("Шедулер запущен. Остановка: Ctrl+C")
        self.logger.info("Шедулер запущен")
        try:
            while True:
                self.load()  # подхватываем задачи, добавленные из другой консоли
                self.run_pending()
                time.sleep(poll_seconds)
        except KeyboardInterrupt:
            self.logger.info("Шедулер остановлен")
            print("\nШедулер остановлен.")


def build_parser():
    p = argparse.ArgumentParser(description="Файловый шедулер")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="добавить задачу")
    a.add_argument("--operation", required=True, choices=OPERATIONS)
    a.add_argument("--source", required=True, help="файл или папка-источник")
    a.add_argument("--destination", help="папка назначения (copy, move, archive)")
    a.add_argument("--schedule", required=True, help="расписание, напр. daily:10:00")

    sub.add_parser("view", help="показать задачи")

    d = sub.add_parser("delete", help="удалить задачу")
    d.add_argument("--id", type=int, required=True)

    r = sub.add_parser("run", help="выполнить задачу сразу")
    r.add_argument("--id", type=int, required=True)

    sub.add_parser("start", help="запустить шедулер")
    sub.add_parser("log", help="показать журнал")
    return p


def ask(prompt, default=None):
    value = input(prompt).strip()
    return value or default


def interactive():
   
    while True:
       
        print("1 - Добавить задачу")
        print("2 - Показать задачи")
        print("3 - Удалить задачу")
        print("4 - Выполнить задачу сейчас")
        print("5 - Запустить шедулер")
        print("6 - Показать журнал")
        print("0 - Выход")
        choice = input("Выберите пункт: ").strip()
        if choice == "1":
            print("Операции: copy, move, delete, archive")
            op = ask("Операция: ")
            src = ask("Источник (файл или папка): ")
            dst = ask("Папка назначения (для delete - Enter): ")
            print("Расписание: daily:10:00 | weekly:fri:18:30 | interval:30 | hourly | once:2026-12-31 23:00")
            sch = ask("Расписание: ")
            main(["add", "--operation", str(op), "--source", str(src), "--schedule", str(sch)]
                 + (["--destination", dst] if dst else []))
        elif choice == "2":
            main(["view"])
        elif choice in ("3", "4"):
            task_id = ask("ID задачи: ")
            if task_id and task_id.isdigit():
                main(["delete" if choice == "3" else "run", "--id", task_id])
            else:
                print("ID должен быть числом.")
        elif choice == "5":
            main(["start"])
        elif choice == "6":
            main(["log"])
        elif choice == "0":
            break
        else:
            print("Неизвестный пункт.")


def main(argv=None):
    args = build_parser().parse_args(argv)
    scheduler = Scheduler()

    if args.command == "add":
        try:
            t = scheduler.add_task(args.operation, args.source, args.destination, args.schedule)
            print(f"Задача добавлена: #{t.task_id}")
        except ValueError as e:
            print(f"Ошибка: {e}")
            return 1
    elif args.command == "view":
        if not scheduler.tasks:
            print("Задач нет.")
        for t in scheduler.tasks:
            print(t)
    elif args.command == "delete":
        if scheduler.remove_task(args.id):
            print(f"Задача #{args.id} удалена.")
        else:
            print(f"Задача #{args.id} не найдена.")
            return 1
    elif args.command == "run":
        task = scheduler.get_task(args.id)
        if not task:
            print(f"Задача #{args.id} не найдена.")
            return 1
        print(f"Результат: {scheduler.run_task(task)}")
    elif args.command == "start":
        scheduler.start()
    elif args.command == "log":
        print(scheduler.logger.read() or "Журнал пуст.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        interactive()
    else:
        sys.exit(main())
