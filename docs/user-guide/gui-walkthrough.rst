GUI Walkthrough
===============

Ana Ekran Bolumleri
-------------------

1. Ust bar: kaynak/hedef secimi, test modu, benzer goruntu secenegi.
2. Is akisi sekmeleri: `Hepsi`, `Kopya Analizi`, `Gruplandirma`.
3. Ayar bolumu: tasima modu, kopya modu, filtreler.
4. Sonuc bolumu: metrik kartlari, kopya tablosu, log akisi.
5. Eylem butonlari: `Onizleme`, `Uygula`, `Duraklat`, `Iptal`, `Geri al`, `Rapor`.

Temel Kullanım
--------------

1. Kaynak klasoru secin.
2. Gruplama yapacaksaniz hedef klasoru secin.
3. Is akisi sekmesinden ne yapmak istediginizi secin.
4. `Onizleme` ile sonucu inceleyin.
5. Kopya gruplarini tablo uzerinden kontrol edin.
6. `Uygula` ile islemi baslatin.

Kopya Grup Kontrolu
-------------------

- Kopya tablosunda satira cift tiklayarak dosya konumunu acabilirsiniz.
- `Grup Detayi` penceresinde hangi dosyalarin korunacagini secebilirsiniz.
- En az bir dosya korunmak zorundadir.

Guvenlik Ozellikleri
--------------------

- Varsayilan kopya modu ``Karantina`` dir.
- `Sil` modu manuel secim gerektirir.
- Uygulama oncesi ozet/teyit diyelogu gosterilir.
- Islem kayitlari transaction dosyalarina yazilir.

Karantina Klasoru
-----------------

Karantina dosyalari su yolda tutulur:

.. code-block:: text

   <target>/.archiflow_quarantine/<timestamp>/

GUI uzerinden `Karantina Klasorunu Ac` ile hizli erisebilirsiniz.

Run Durumlari
-------------

- `Hazir`: Islem yok.
- `Calisiyor`: Pipeline aktif.
- `Duraklatildi`: Gecici durdurma.
- `Iptal edildi`: Kullanici/uygulama tarafindan iptal.
- `Tamamlandi`: Islem bitti.
