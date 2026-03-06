Contributing Guidelines
=======================

Temel Ilkeler
-------------

Bu proje guvenlik, deterministik davranis ve veri kaybi riskinin azaltilmasi odaklidir.

Katki prensipleri:

1. Degisiklikleri tek konuya odakli tut.
2. Davranis degisikligi varsa test ekle.
3. Kullaniciya etkisi olan degisiklikte docs guncelle.
4. Destructive operasyonlarda guvenlik varsayilanlarini koru.

Kod Kalite Kapisi
-----------------

PR oncesi asagidaki komutlarin temiz gecmesi beklenir:

.. code-block:: bash

   black --check archiflow tests main.py
   isort --check-only archiflow tests main.py
   flake8 archiflow tests main.py
   mypy archiflow
   pytest -q

Tek komut akisi:

.. code-block:: bash

   tox -e format,lint,type,py313

Katki Akisi
-----------

1. Branch ac
2. Kod + test + docs guncelle
3. CI green olana kadar duzelt
4. Acik, teknik commit mesajlariyla PR ac

Commit ve PR Notlari
--------------------

- Commit mesajlari davranis odakli olmali.
- Masterplan fazina dokunan degisikliklerde ilgili kutular guncellenmeli.
- GUI degisikliklerinde mumkunse ekran goruntusu veya acik adim eklenmeli.

Ilgili Dosyalar
---------------

- Genel katki rehberi: `CONTRIBUTING.md`
- CI akisi: `.github/workflows/ci.yml`
- QA konfigurasyon: `pyproject.toml`, `setup.cfg`, `tox.ini`
