Development Setup
=================

Ortam Kurulumu
--------------

.. code-block:: bash

   git clone <repo-url>
   cd ArchiFlow
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt
   python3 -m pip install -e .[dev]

Proje Giris Noktalari
---------------------

- GUI: `python3 main.py gui`
- CLI: `python3 main.py <command>`

Dokumantasyon Build
-------------------

.. code-block:: bash

   source .venv/bin/activate
   make -C docs html

UI/CLI Hizli Smoke Komutlari
----------------------------

CLI smoke:

.. code-block:: bash

   python3 main.py scan --source /tmp/sample
   python3 main.py preview --source /tmp/sample

GUI smoke:

.. code-block:: bash

   python3 main.py gui

Performans Araclari
-------------------

.. code-block:: bash

   python tests/performance/run_benchmark.py \
     --source /tmp/archiflow_perf \
     --generate \
     --files 5000 \
     --duplicate-ratio 0.2 \
     --same-size-ratio 0.1 \
     --iterations 2

Yaygin Gelistirme Notlari
-------------------------

- macOS/Homebrew Python'da sistem pip yerine sanal ortam kullanin.
- `qdarktheme` opsiyoneldir, yoksa fallback theme kullanilir.
- Sphinx build su an Requests versiyon uyari mesaji verebilir; build'i bozmaz.
