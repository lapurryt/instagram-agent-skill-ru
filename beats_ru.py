#!/usr/bin/env python3
# Старый путь. С 23.11.2026 скрипт лежит в skills/ig-reel/beats_ru.py (ig-ru разложен 1 в 1 как репозиторий Джейка).
# Этот файл только запускает новый, чтобы старые команды не падали. Новые команды пиши с новым путём.
import os, runpy, sys
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "skills", "ig-reel", "beats_ru.py")
sys.argv[0] = p
runpy.run_path(p, run_name="__main__")
