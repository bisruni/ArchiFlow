Class Diagrams
==============

Bu bolumde cekirdek sinif iliskileri metin tabanli diagramlarla ozetlenir.

Core Pipeline Diagram
---------------------

.. code-block:: text

   ArchiFlowEngine
      |
      +-- FileScanner
      +-- DuplicateDetector
      +-- FileOrganizer
      +-- TransactionService
      +-- ReportExporter

Data Model Diagram
------------------

.. code-block:: text

   OperationReportData
      |
      +-- OperationSummary
      +-- [DuplicateGroup]
      |      |
      |      +-- [FileRecord]
      |
      +-- [SimilarImageGroup]
      +-- transaction_id / transaction_file_path

Transaction Diagram
-------------------

.. code-block:: text

   OperationTransaction
      |
      +-- transaction_id
      +-- source_root
      +-- target_root
      +-- [TransactionEntry]
             |
             +-- action: TransactionAction
             +-- status: TransactionStatus
             +-- source_path
             +-- destination_path
             +-- error_message

Enum Model Diagram
------------------

.. code-block:: text

   Enum Types (archiflow.models)
   - FileCategory
   - OrganizationMode
   - DedupeMode
   - ExecutionScope
   - OperationStage
   - TransactionAction
   - TransactionStatus
