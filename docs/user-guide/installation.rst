Installation Guide
==================

Sistem Gereksinimleri
---------------------

- Python 3.10+
- `pip`
- (Opsiyonel GUI) PySide6

Adim Adim Kurulum
-----------------

1. Proje klasorune girin.
2. Sanal ortam olusturun.
3. Sanal ortami aktif edin.
4. Bagimliliklari yukleyin.

.. code-block:: bash

   cd /path/to/ArchiFlow
   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt

Gelistirme araclarini da kurmak icin:

.. code-block:: bash

   python3 -m pip install -e .[dev]

Kurulum Dogrulama
-----------------

CLI yardim ekranini acin:

.. code-block:: bash

   python3 main.py -h

Testleri calistirin:

.. code-block:: bash

   pytest -q

Sik Karsilasilan Kurulum Sorunlari
----------------------------------

`externally-managed-environment` hatasi (macOS/Homebrew Python):

.. code-block:: bash

   python3 -m venv .venv
   source .venv/bin/activate
   python3 -m pip install -r requirements.txt

GUI bagimliligi eksikse:

.. code-block:: bash

   source .venv/bin/activate
   python3 -m pip install PySide6
