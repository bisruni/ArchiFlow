Architecture Overview
=====================

Yuksek Seviye Katmanlar
-----------------------

ArchiFlow moduler bir servis yapisi kullanir:

1. Tarama katmani (`scanner`)
2. Analiz katmani (`duplicate_detector`)
3. Uygulama katmani (`organizer`)
4. Orkestrasyon katmani (`pipeline`)
5. Durum/kalicilik katmanlari (`transaction_service`, `hash_cache`, `profile_service`)
6. Arayuz katmanlari (`gui`, `cli`)

Katman Sorumluluklari
---------------------

`archiflow.scanner`
~~~~~~~~~~~~~~~~~~~~~

- Dosya sistemini gezer.
- Filtreleri uygular.
- `FileRecord` listesi uretir.

`archiflow.duplicate_detector`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Kesin kopya tespiti yapar.
- Opsiyonel benzer goruntu analizi calistirir.

`archiflow.organizer`
~~~~~~~~~~~~~~~~~~~~~~~

- Kopya dosyalari secilen moda gore isler (`quarantine`, `delete`).
- Gruplama modunda dosyalari kategori/yil/ay yapisina tasir veya kopyalar.
- Her operasyonu transaction journal ile kaydeder.

`archiflow.pipeline`
~~~~~~~~~~~~~~~~~~~~~~

- Tum servisleri sirali sekilde baglar.
- Run lifecycle yonetimi yapar.
- Rapor uretimini tetikler.

`archiflow.transaction_service`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Transaction dosyalarini kaydeder/yukler.
- Undo akisini ters sirada uygular.

`archiflow.hash_cache`
~~~~~~~~~~~~~~~~~~~~~~~~

- Hash hesaplarini path/size/mtime anahtariyla cache'ler.

`archiflow.gui` ve `archiflow.cli`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

- Kullanici etkileseimini saglar.
- Pipeline calistirma parametrelerini olusturur.

Data Flow
---------

.. code-block:: text

   source_path
      -> scanner.scan()
      -> duplicate_detector.find_duplicates()
      -> (opsiyonel) organizer.process_duplicates()
      -> (opsiyonel) organizer.organize_by_category_and_date()
      -> report_exporter.export()
      -> summary + transaction + reports

State ve Recovery
-----------------

- Islem baslamadan transaction dosyasi acilir.
- Her dosya operasyonu journal entry olarak yazilir.
- Cancel/exception durumunda final flush yapilir.
- Undo, DONE entry'leri ters sirada geri alir.
