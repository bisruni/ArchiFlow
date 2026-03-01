using Avalonia.Threading;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using FileGrouper.Models;
using FileGrouper.Services;
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace FileGrouper.ViewModels;

public partial class MainWindowViewModel : ObservableObject
{
    private const string ScopeGroupAndDedupe = "GroupAndDedupe";
    private const string ScopeGroupOnly = "GroupOnly";
    private const string ScopeDedupeOnly = "DedupeOnly";

    private readonly FileScanner _scanner = new();
    private readonly DuplicateDetector _detector = new();
    private readonly FileOrganizer _organizer = new();
    private readonly TransactionService _transactionService = new();
    private readonly ReportExporter _reportExporter = new();
    private readonly ProfileService _profileService = new();

    private CancellationTokenSource? _runCts;
    private PauseController? _pauseController;
    private IReadOnlyList<DuplicateGroup> _lastDuplicateGroups = [];
    private IReadOnlyList<SimilarImageGroup> _lastSimilarGroups = [];
    private OperationSummary? _lastSummary;
    private string? _lastSource;
    private string? _lastTarget;
    private string? _lastTransactionFile;
    private readonly Dictionary<string, OperationProfile> _profileMap = new(StringComparer.OrdinalIgnoreCase);

    [ObservableProperty]
    private string _selectedLanguage = "Türkçe";

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(PreviewCommand))]
    [NotifyCanExecuteChangedFor(nameof(ApplyCommand))]
    private string _sourcePath = string.Empty;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ApplyCommand))]
    [NotifyCanExecuteChangedFor(nameof(UndoCommand))]
    private string _targetPath = string.Empty;

    [ObservableProperty]
    private string _selectedOrganizationMode = string.Empty;

    [ObservableProperty]
    private string _selectedDedupeMode = string.Empty;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(ApplyCommand))]
    private string _selectedExecutionScope = string.Empty;

    [ObservableProperty]
    private bool _isDryRun = true;

    [ObservableProperty]
    [NotifyCanExecuteChangedFor(nameof(PreviewCommand))]
    [NotifyCanExecuteChangedFor(nameof(ApplyCommand))]
    [NotifyCanExecuteChangedFor(nameof(PauseResumeCommand))]
    [NotifyCanExecuteChangedFor(nameof(CancelCommand))]
    [NotifyCanExecuteChangedFor(nameof(UndoCommand))]
    private bool _isBusy;

    [ObservableProperty]
    private bool _isPaused;

    [ObservableProperty]
    private string _pauseResumeButtonText = "Duraklat";

    [ObservableProperty]
    private string _status = string.Empty;

    [ObservableProperty]
    private int _totalFiles;

    [ObservableProperty]
    private string _totalSize = "0 B";

    [ObservableProperty]
    private int _duplicateGroups;

    [ObservableProperty]
    private int _duplicateFiles;

    [ObservableProperty]
    private string _reclaimableSize = "0 B";

    [ObservableProperty]
    private int _filesCopied;

    [ObservableProperty]
    private int _filesMoved;

    [ObservableProperty]
    private int _duplicatesQuarantined;

    [ObservableProperty]
    private int _duplicatesDeleted;

    [ObservableProperty]
    private int _errorCount;

    [ObservableProperty]
    private int _similarImageGroups;

    [ObservableProperty]
    private DateTimeOffset? _lastRunAt;

    [ObservableProperty]
    private string _windowTitle = "FileGrouper";

    [ObservableProperty]
    private string _pageTitle = string.Empty;

    [ObservableProperty]
    private string _pageSubtitle = string.Empty;

    [ObservableProperty]
    private string _languageLabel = string.Empty;

    [ObservableProperty]
    private string _safeModeLabel = string.Empty;

    [ObservableProperty]
    private string _dryRunOnText = string.Empty;

    [ObservableProperty]
    private string _dryRunOffText = string.Empty;

    [ObservableProperty]
    private string _modeExplanationText = string.Empty;

    [ObservableProperty]
    private string _workspaceTitle = string.Empty;

    [ObservableProperty]
    private string _workspaceSubtitle = string.Empty;

    [ObservableProperty]
    private string _sourceFolderLabel = string.Empty;

    [ObservableProperty]
    private string _targetFolderLabel = string.Empty;

    [ObservableProperty]
    private string _sourceWatermark = string.Empty;

    [ObservableProperty]
    private string _targetWatermark = string.Empty;

    [ObservableProperty]
    private string _browseButtonText = string.Empty;

    [ObservableProperty]
    private string _organizationModeLabel = string.Empty;

    [ObservableProperty]
    private string _duplicateModeLabel = string.Empty;

    [ObservableProperty]
    private string _executionScopeLabel = string.Empty;

    [ObservableProperty]
    private string _previewButtonText = string.Empty;

    [ObservableProperty]
    private string _applyButtonText = string.Empty;

    [ObservableProperty]
    private string _swapButtonText = string.Empty;

    [ObservableProperty]
    private string _operationOutputTitle = string.Empty;

    [ObservableProperty]
    private string _operationOutputLine1 = string.Empty;

    [ObservableProperty]
    private string _operationOutputLine2 = string.Empty;

    [ObservableProperty]
    private string _quickStartTitle = string.Empty;

    [ObservableProperty]
    private string _quickStartLine1 = string.Empty;

    [ObservableProperty]
    private string _quickStartLine2 = string.Empty;

    [ObservableProperty]
    private string _quickStartLine3 = string.Empty;

    [ObservableProperty]
    private string _totalFilesLabel = string.Empty;

    [ObservableProperty]
    private string _totalSizeLabel = string.Empty;

    [ObservableProperty]
    private string _duplicateFilesLabel = string.Empty;

    [ObservableProperty]
    private string _reclaimableLabel = string.Empty;

    [ObservableProperty]
    private string _errorsLabel = string.Empty;

    [ObservableProperty]
    private string _duplicateGroupsTitle = string.Empty;

    [ObservableProperty]
    private string _logStreamTitle = string.Empty;

    [ObservableProperty]
    private string _clearButtonText = string.Empty;

    [ObservableProperty]
    private string _busyLabel = string.Empty;

    [ObservableProperty]
    private string _groupsSummary = string.Empty;

    [ObservableProperty]
    private string _copiedSummary = string.Empty;

    [ObservableProperty]
    private string _movedSummary = string.Empty;

    [ObservableProperty]
    private string _quarantinedSummary = string.Empty;

    [ObservableProperty]
    private string _lastRunDisplay = string.Empty;

    [ObservableProperty]
    private string _sourceDialogTitle = string.Empty;

    [ObservableProperty]
    private string _targetDialogTitle = string.Empty;

    [ObservableProperty]
    private string _nonLocalPathStatus = string.Empty;

    [ObservableProperty]
    private string _errorPrefix = "HATA";

    [ObservableProperty]
    private string _pathValidationTitle = string.Empty;

    [ObservableProperty]
    private string _pathValidationText = string.Empty;

    [ObservableProperty]
    private string _progressTitle = string.Empty;

    [ObservableProperty]
    private string _progressStatus = string.Empty;

    [ObservableProperty]
    private int _progressCurrent;

    [ObservableProperty]
    private int _progressTotal;

    [ObservableProperty]
    private double _progressPercent;

    [ObservableProperty]
    private string _pauseButtonText = string.Empty;

    [ObservableProperty]
    private string _cancelButtonText = string.Empty;

    [ObservableProperty]
    private string _undoButtonText = string.Empty;

    [ObservableProperty]
    private string _exportReportButtonText = string.Empty;

    [ObservableProperty]
    private string _advancedTitle = string.Empty;

    [ObservableProperty]
    private string _filtersTitle = string.Empty;

    [ObservableProperty]
    private string _includeExtLabel = string.Empty;

    [ObservableProperty]
    private string _excludeExtLabel = string.Empty;

    [ObservableProperty]
    private string _minSizeLabel = string.Empty;

    [ObservableProperty]
    private string _maxSizeLabel = string.Empty;

    [ObservableProperty]
    private string _fromDateLabel = string.Empty;

    [ObservableProperty]
    private string _toDateLabel = string.Empty;

    [ObservableProperty]
    private string _excludeHiddenLabel = string.Empty;

    [ObservableProperty]
    private string _excludeSystemLabel = string.Empty;

    [ObservableProperty]
    private string _similarImagesLabel = string.Empty;

    [ObservableProperty]
    private string _profilesTitle = string.Empty;

    [ObservableProperty]
    private string _profileNameLabel = string.Empty;

    [ObservableProperty]
    private string _saveProfileButtonText = string.Empty;

    [ObservableProperty]
    private string _applyProfileButtonText = string.Empty;

    [ObservableProperty]
    private string _reportStatus = string.Empty;

    [ObservableProperty]
    private string _includeExtensionsText = string.Empty;

    [ObservableProperty]
    private string _excludeExtensionsText = string.Empty;

    [ObservableProperty]
    private string _minSizeMbText = string.Empty;

    [ObservableProperty]
    private string _maxSizeMbText = string.Empty;

    [ObservableProperty]
    private string _fromDateText = string.Empty;

    [ObservableProperty]
    private string _toDateText = string.Empty;

    [ObservableProperty]
    private bool _excludeHiddenFiles = true;

    [ObservableProperty]
    private bool _excludeSystemFiles = true;

    [ObservableProperty]
    private bool _detectSimilarImages;

    [ObservableProperty]
    private string _selectedProfileName = string.Empty;

    [ObservableProperty]
    private string _newProfileName = string.Empty;

    public ObservableCollection<string> Languages { get; } = ["Türkçe", "English"];
    public ObservableCollection<string> OrganizationModes { get; } = [];
    public ObservableCollection<string> DedupeModes { get; } = [];
    public ObservableCollection<string> ExecutionScopes { get; } = [];
    public ObservableCollection<string> Profiles { get; } = [];
    public ObservableCollection<DuplicatePreviewItem> DuplicateItems { get; } = [];
    public ObservableCollection<string> SimilarImageItems { get; } = [];
    public ObservableCollection<string> LogLines { get; } = [];

    public MainWindowViewModel()
    {
        ApplyLanguage();
        RebuildModeCollections();
        LoadProfiles();
        Status = Tr("Hazır", "Ready");
        UpdateModeExplanation();
        UpdatePathValidationInfo();
        ProgressStatus = Tr("Beklemede", "Idle");
    }

    [RelayCommand(CanExecute = nameof(CanRunPreview))]
    private async Task Preview()
    {
        await RunPipelineAsync(applyChanges: false);
    }

    [RelayCommand(CanExecute = nameof(CanRunApply))]
    private async Task Apply()
    {
        await RunPipelineAsync(applyChanges: true);
    }

    [RelayCommand(CanExecute = nameof(CanPauseOrResume))]
    private void PauseResume()
    {
        if (_pauseController is null)
        {
            return;
        }

        if (IsPaused)
        {
            _pauseController.Resume();
            IsPaused = false;
            PauseResumeButtonText = Tr("Duraklat", "Pause");
            Status = Tr("İşlem devam ediyor...", "Operation resumed...");
        }
        else
        {
            _pauseController.Pause();
            IsPaused = true;
            PauseResumeButtonText = Tr("Devam Et", "Resume");
            Status = Tr("İşlem duraklatıldı.", "Operation paused.");
        }
    }

    [RelayCommand(CanExecute = nameof(CanCancel))]
    private void Cancel()
    {
        _runCts?.Cancel();
        Status = Tr("İptal isteği gönderildi...", "Cancellation requested...");
    }

    [RelayCommand(CanExecute = nameof(CanUndo))]
    private async Task Undo()
    {
        if (string.IsNullOrWhiteSpace(TargetPath))
        {
            Status = Tr("Undo için hedef klasör seçin.", "Select target folder for undo.");
            return;
        }

        BeginOperation();
        Status = Tr("Son işlem geri alınıyor...", "Undoing last transaction...");
        ProgressStatus = Tr("Geri alma", "Undo");

        try
        {
            var target = Path.GetFullPath(TargetPath);
            var summary = await Task.Run(() =>
                _transactionService.UndoLastTransaction(target, msg => RunOnUi(() => LogLines.Add(msg))));

            ApplySummary(summary);
            LastRunAt = DateTimeOffset.Now;
            Status = Tr("Geri alma tamamlandı.", "Undo completed.");
        }
        catch (Exception ex)
        {
            LogLines.Add($"{ErrorPrefix}: {ex.Message}");
            Status = Tr("Geri alma başarısız oldu.", "Undo failed.");
        }
        finally
        {
            EndOperation();
        }
    }

    [RelayCommand(CanExecute = nameof(CanExportReport))]
    private void ExportReport()
    {
        if (_lastSummary is null || string.IsNullOrWhiteSpace(_lastSource) || string.IsNullOrWhiteSpace(_lastTarget))
        {
            Status = Tr("Önce Preview veya Apply çalıştırın.", "Run Preview or Apply first.");
            return;
        }

        try
        {
            var outputDir = Path.Combine(_lastTarget, ".filegrouper", "reports");
            var report = new OperationReportData
            {
                SourcePath = _lastSource,
                TargetPath = _lastTarget,
                Summary = _lastSummary,
                DuplicateGroups = _lastDuplicateGroups,
                SimilarImageGroups = _lastSimilarGroups,
                TransactionFilePath = _lastTransactionFile
            };

            var exported = _reportExporter.Export(report, outputDir);
            ReportStatus = $"{Path.GetFileName(exported.JsonPath)}, {Path.GetFileName(exported.CsvPath)}, {Path.GetFileName(exported.PdfPath)}";
            Status = Tr("Raporlar dışa aktarıldı.", "Reports exported.");
        }
        catch (Exception ex)
        {
            LogLines.Add($"{ErrorPrefix}: {ex.Message}");
            Status = Tr("Rapor dışa aktarma başarısız.", "Report export failed.");
        }
    }

    [RelayCommand]
    private void ApplyProfile()
    {
        if (!_profileMap.TryGetValue(SelectedProfileName, out var profile))
        {
            Status = Tr("Profil bulunamadı.", "Profile not found.");
            return;
        }

        SetProfileToUi(profile);
        Status = Tr("Profil uygulandı.", "Profile applied.");
    }

    [RelayCommand]
    private void SaveProfile()
    {
        var name = string.IsNullOrWhiteSpace(NewProfileName)
            ? $"Custom {DateTime.Now:yyyyMMdd_HHmmss}"
            : NewProfileName.Trim();

        var profile = BuildProfile(name);
        _profileService.UpsertProfile(profile);
        LoadProfiles();
        SelectedProfileName = name;
        Status = Tr("Profil kaydedildi.", "Profile saved.");
    }

    [RelayCommand]
    private void ClearLogs()
    {
        LogLines.Clear();
        Status = Tr("Loglar temizlendi.", "Logs cleared.");
    }

    [RelayCommand]
    private void SwapPaths()
    {
        (SourcePath, TargetPath) = (TargetPath, SourcePath);
    }

    private async Task RunPipelineAsync(bool applyChanges)
    {
        var includeGrouping = ScopeIncludesGrouping();
        var includeDedupe = ScopeIncludesDuplicateWork();

        if (!CanRunPreview())
        {
            Status = Tr("Geçerli bir kaynak klasör seçin.", "Select a valid source folder.");
            return;
        }

        if (applyChanges && !CanRunApply())
        {
            Status = Tr("Seçili işleme göre gerekli klasörleri ayarlayın.", "Set required folders for selected operation.");
            return;
        }

        if (applyChanges && !includeGrouping && !includeDedupe)
        {
            Status = Tr("En az bir işlem seçin: Gruplama veya Kopya Temizleme.", "Select at least one action: Grouping or Duplicate Cleanup.");
            return;
        }

        if (applyChanges && !ValidatePaths(out var pathError))
        {
            Status = pathError;
            LogLines.Add($"{ErrorPrefix}: {pathError}");
            return;
        }

        BeginOperation();
        Status = applyChanges
            ? includeGrouping && includeDedupe
                ? Tr("Gruplama ve kopya temizleme uygulanıyor...", "Applying grouping and duplicate cleanup...")
                : includeGrouping
                    ? Tr("Gruplama uygulanıyor...", "Applying grouping...")
                    : Tr("Kopya temizleme uygulanıyor...", "Applying duplicate cleanup...")
            : Tr("Önizleme hazırlanıyor...", "Preparing preview...");

        LogLines.Clear();
        DuplicateItems.Clear();
        SimilarImageItems.Clear();

        var source = Path.GetFullPath(SourcePath);
        var target = includeGrouping && !string.IsNullOrWhiteSpace(TargetPath)
            ? Path.GetFullPath(TargetPath)
            : source;
        var mode = ParseOrganizationMode();
        var dedupeMode = ParseDedupeMode();
        var filter = BuildFilterOptions();
        var logBuffer = new ConcurrentQueue<string>();

        try
        {
            var result = await Task.Run(() =>
            {
                HashCacheService? hashCache = null;
                if (includeDedupe)
                {
                    var cachePath = Path.Combine(source, ".filegrouper", "cache", "hash-cache.db");
                    hashCache = new HashCacheService(cachePath);
                }

                var scanOptions = new ScanExecutionOptions
                {
                    Filter = filter,
                    Log = msg => logBuffer.Enqueue(msg),
                    Progress = OnProgress,
                    CancellationToken = _runCts!.Token,
                    PauseController = _pauseController
                };

                var files = _scanner.Scan(source, scanOptions);

                var detection = includeDedupe
                    ? _detector.FindDuplicateData(files, new DuplicateDetectionOptions
                    {
                        Log = msg => logBuffer.Enqueue(msg),
                        Progress = OnProgress,
                        CancellationToken = _runCts!.Token,
                        PauseController = _pauseController,
                        HashCache = hashCache,
                        DetectSimilarImages = DetectSimilarImages
                    })
                    : new DuplicateDetectionResult([], []);

                var summary = BuildOperationSummary(files, detection.DuplicateGroups);

                string? txPath = null;
                if (applyChanges)
                {
                    var transaction = new OperationTransaction
                    {
                        SourceRoot = source,
                        TargetRoot = target
                    };

                    var organizeOptions = new OrganizeExecutionOptions
                    {
                        Log = msg => logBuffer.Enqueue(msg),
                        Progress = OnProgress,
                        CancellationToken = _runCts!.Token,
                        PauseController = _pauseController,
                        Transaction = transaction
                    };

                    IReadOnlyList<FileRecord> filesToSkip = [];
                    if (includeDedupe)
                    {
                        filesToSkip = _organizer.ProcessDuplicates(
                            detection.DuplicateGroups,
                            dedupeMode,
                            source,
                            IsDryRun,
                            summary,
                            organizeOptions);
                    }

                    if (includeGrouping)
                    {
                        var skipSet = filesToSkip.Select(f => f.FullPath).ToHashSet(StringComparer.OrdinalIgnoreCase);
                        var remaining = files.Where(f => !skipSet.Contains(f.FullPath)).ToArray();

                        _organizer.OrganizeByCategoryAndDate(
                            remaining,
                            target,
                            mode,
                            IsDryRun,
                            summary,
                            organizeOptions);
                    }

                    if (!IsDryRun && transaction.Entries.Count > 0)
                    {
                        txPath = _transactionService.SaveTransaction(transaction);
                    }
                }

                return (files, detection, summary, txPath);
            });

            ApplySummary(result.summary);
            UpdateDuplicatePreview(result.detection.DuplicateGroups);
            UpdateSimilarPreview(result.detection.SimilarImageGroups);
            FlushLogs(logBuffer);
            LastRunAt = DateTimeOffset.Now;
            _lastSummary = result.summary;
            _lastDuplicateGroups = result.detection.DuplicateGroups;
            _lastSimilarGroups = result.detection.SimilarImageGroups;
            _lastSource = source;
            _lastTarget = target;
            _lastTransactionFile = result.txPath;
            UpdatePathValidationInfo();

            Status = applyChanges
                ? (IsDryRun
                    ? Tr("Test çalıştırıldı. Dosyalarda değişiklik yapılmadı.", "Dry run completed. No file changes.")
                    : Tr("Seçili işlem tamamlandı.", "Selected operation completed."))
                : Tr("Önizleme tamamlandı.", "Preview completed.");
        }
        catch (OperationCanceledException)
        {
            Status = Tr("İşlem iptal edildi.", "Operation cancelled.");
        }
        catch (Exception ex)
        {
            LogLines.Add($"{ErrorPrefix}: {ex.Message}");
            Status = Tr("İşlem başarısız oldu.", "Operation failed.");
        }
        finally
        {
            EndOperation();
        }
    }

    private void OnProgress(OperationProgress progress)
    {
        RunOnUi(() =>
        {
            ProgressCurrent = progress.ProcessedFiles;
            ProgressTotal = progress.TotalFiles;
            ProgressPercent = progress.TotalFiles > 0
                ? (double)progress.ProcessedFiles / progress.TotalFiles * 100.0
                : 0;

            ProgressStatus = progress.Stage switch
            {
                OperationStage.Scanning => Tr("Taranıyor", "Scanning"),
                OperationStage.Hashing => Tr("Hash hesaplanıyor", "Hashing"),
                OperationStage.Similarity => Tr("Benzer görseller aranıyor", "Finding similar images"),
                OperationStage.Organizing => Tr("Dosyalar düzenleniyor", "Organizing"),
                _ => progress.Message
            };
        });
    }

    private void BeginOperation()
    {
        IsBusy = true;
        IsPaused = false;
        PauseResumeButtonText = Tr("Duraklat", "Pause");
        _runCts = new CancellationTokenSource();
        _pauseController = new PauseController();
        ProgressCurrent = 0;
        ProgressTotal = 0;
        ProgressPercent = 0;
        ProgressStatus = Tr("Başlatıldı", "Started");
    }

    private void EndOperation()
    {
        IsBusy = false;
        IsPaused = false;
        _pauseController?.Resume();
        _pauseController = null;
        _runCts?.Dispose();
        _runCts = null;
        PauseResumeButtonText = Tr("Duraklat", "Pause");
    }

    private void UpdateDuplicatePreview(IReadOnlyList<DuplicateGroup> duplicates)
    {
        DuplicateItems.Clear();
        foreach (var group in duplicates.Take(30))
        {
            var keep = group.Files.FirstOrDefault()?.FullPath ?? "-";
            DuplicateItems.Add(
                new DuplicatePreviewItem
                {
                    HashPrefix = group.Hash.Length >= 12 ? group.Hash[..12] : group.Hash,
                    KeepPath = keep,
                    RemoveCount = Math.Max(0, group.Files.Count - 1),
                    FileSize = FormatSize(group.SizeBytes)
                });
        }
    }

    private void UpdateSimilarPreview(IReadOnlyList<SimilarImageGroup> similarGroups)
    {
        SimilarImageItems.Clear();
        foreach (var group in similarGroups.Take(25))
        {
            SimilarImageItems.Add($"{Path.GetFileName(group.AnchorPath)} (+{group.SimilarPaths.Count})");
        }

        SimilarImageGroups = similarGroups.Count;
    }

    private void ApplySummary(OperationSummary summary)
    {
        TotalFiles = summary.TotalFilesScanned;
        TotalSize = FormatSize(summary.TotalBytesScanned);
        DuplicateGroups = summary.DuplicateGroupCount;
        DuplicateFiles = summary.DuplicateFilesFound;
        ReclaimableSize = FormatSize(summary.DuplicateBytesReclaimable);
        FilesCopied = summary.FilesCopied;
        FilesMoved = summary.FilesMoved;
        DuplicatesQuarantined = summary.DuplicatesQuarantined;
        DuplicatesDeleted = summary.DuplicatesDeleted;
        ErrorCount = summary.Errors.Count;

        foreach (var error in summary.Errors.Take(100))
        {
            LogLines.Add($"{ErrorPrefix}: {error}");
        }
    }

    private void FlushLogs(ConcurrentQueue<string> logs)
    {
        foreach (var line in logs.Take(500))
        {
            LogLines.Add(line);
        }
    }

    private bool CanRunPreview() => !IsBusy && Directory.Exists(SourcePath);
    private bool CanRunApply()
    {
        if (IsBusy || !Directory.Exists(SourcePath))
        {
            return false;
        }

        var includeGrouping = ScopeIncludesGrouping();
        var includeDedupe = ScopeIncludesDuplicateWork();
        if (!includeGrouping && !includeDedupe)
        {
            return false;
        }

        return !includeGrouping || !string.IsNullOrWhiteSpace(TargetPath);
    }

    private bool CanPauseOrResume() => IsBusy;
    private bool CanCancel() => IsBusy;
    private bool CanUndo() => !IsBusy && !string.IsNullOrWhiteSpace(TargetPath);
    private bool CanExportReport() => _lastSummary is not null;

    private bool ValidatePaths(out string error)
    {
        var pathError = GetPathValidationError();
        error = pathError ?? string.Empty;
        return pathError is null;
    }

    private ScanFilterOptions BuildFilterOptions()
    {
        return new ScanFilterOptions
        {
            IncludeExtensions = ParseExtensions(IncludeExtensionsText),
            ExcludeExtensions = ParseExtensions(ExcludeExtensionsText),
            MinSizeBytes = ParseSizeMb(MinSizeMbText),
            MaxSizeBytes = ParseSizeMb(MaxSizeMbText),
            FromUtc = ParseDateUtc(FromDateText),
            ToUtc = ParseDateUtc(ToDateText),
            ExcludeHidden = ExcludeHiddenFiles,
            ExcludeSystem = ExcludeSystemFiles
        };
    }

    private OperationProfile BuildProfile(string name)
    {
        return new OperationProfile
        {
            Name = name,
            ExecutionScope = ParseExecutionScopeKey(),
            OrganizationMode = ParseOrganizationMode(),
            DedupeMode = ParseDedupeMode(),
            IsDryRun = IsDryRun,
            DetectSimilarImages = DetectSimilarImages,
            Filter = BuildFilterOptions()
        };
    }

    private void SetProfileToUi(OperationProfile profile)
    {
        SelectedOrganizationMode = profile.OrganizationMode == OrganizationMode.Move
            ? OrganizationModes[1]
            : OrganizationModes[0];

        SelectedDedupeMode = profile.DedupeMode switch
        {
            DedupeMode.Off => DedupeModes[1],
            DedupeMode.Delete => DedupeModes[2],
            _ => DedupeModes[0]
        };

        IsDryRun = profile.IsDryRun;
        DetectSimilarImages = profile.DetectSimilarImages;
        SelectedExecutionScope = ScopeLabelFromKey(profile.ExecutionScope);
        IncludeExtensionsText = string.Join(", ", profile.Filter.IncludeExtensions);
        ExcludeExtensionsText = string.Join(", ", profile.Filter.ExcludeExtensions);
        MinSizeMbText = ToMbText(profile.Filter.MinSizeBytes);
        MaxSizeMbText = ToMbText(profile.Filter.MaxSizeBytes);
        FromDateText = profile.Filter.FromUtc?.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) ?? string.Empty;
        ToDateText = profile.Filter.ToUtc?.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) ?? string.Empty;
        ExcludeHiddenFiles = profile.Filter.ExcludeHidden;
        ExcludeSystemFiles = profile.Filter.ExcludeSystem;
    }

    private void LoadProfiles()
    {
        var loaded = _profileService.LoadProfiles();
        _profileMap.Clear();
        Profiles.Clear();

        foreach (var profile in loaded)
        {
            Profiles.Add(profile.Name);
            _profileMap[profile.Name] = profile;
        }

        if (Profiles.Count > 0)
        {
            SelectedProfileName = Profiles[0];
        }
    }

    private OrganizationMode ParseOrganizationMode()
    {
        return IsMoveSelection(SelectedOrganizationMode)
            ? OrganizationMode.Move
            : OrganizationMode.Copy;
    }

    private DedupeMode ParseDedupeMode()
    {
        if (SelectedDedupeMode.Equals("Off", StringComparison.OrdinalIgnoreCase)
            || SelectedDedupeMode.Equals("Kapalı", StringComparison.OrdinalIgnoreCase))
        {
            return DedupeMode.Off;
        }

        if (SelectedDedupeMode.Equals("Delete", StringComparison.OrdinalIgnoreCase)
            || SelectedDedupeMode.Equals("Sil", StringComparison.OrdinalIgnoreCase))
        {
            return DedupeMode.Delete;
        }

        return DedupeMode.Quarantine;
    }

    private string ParseExecutionScopeKey()
    {
        if (SelectedExecutionScope.Equals("Group Only", StringComparison.OrdinalIgnoreCase)
            || SelectedExecutionScope.Equals("Sadece Grupla", StringComparison.OrdinalIgnoreCase))
        {
            return ScopeGroupOnly;
        }

        if (SelectedExecutionScope.Equals("Duplicate Cleanup Only", StringComparison.OrdinalIgnoreCase)
            || SelectedExecutionScope.Equals("Sadece Kopya Temizle", StringComparison.OrdinalIgnoreCase))
        {
            return ScopeDedupeOnly;
        }

        return ScopeGroupAndDedupe;
    }

    private string ScopeLabelFromKey(string scopeKey)
    {
        return scopeKey switch
        {
            ScopeGroupOnly => Tr("Sadece Grupla", "Group Only"),
            ScopeDedupeOnly => Tr("Sadece Kopya Temizle", "Duplicate Cleanup Only"),
            _ => Tr("Grupla + Kopya Temizle", "Group + Duplicate Cleanup")
        };
    }

    private bool ScopeIncludesGrouping() => ParseExecutionScopeKey() != ScopeDedupeOnly;
    private bool ScopeIncludesDuplicateWork() => ParseExecutionScopeKey() != ScopeGroupOnly;

    private bool IsMoveSelection(string mode)
    {
        return mode.Equals("Move", StringComparison.OrdinalIgnoreCase)
            || mode.Equals("Taşı", StringComparison.OrdinalIgnoreCase);
    }

    private string? GetPathValidationError()
    {
        if (string.IsNullOrWhiteSpace(SourcePath))
        {
            return Tr(
                "Kaynak klasör seçin. Örnek: /Volumes/USB",
                "Select source folder. Example: /Volumes/USB");
        }

        if (!Directory.Exists(SourcePath))
        {
            return Tr("Kaynak klasör bulunamadı.", "Source folder was not found.");
        }

        if (!ScopeIncludesGrouping())
        {
            return null;
        }

        if (string.IsNullOrWhiteSpace(TargetPath))
        {
            return Tr(
                "Gruplama için hedef klasör seçin. Örnek: /Volumes/USB_Organized",
                "Select target folder for grouping. Example: /Volumes/USB_Organized");
        }

        var source = Path.GetFullPath(SourcePath);
        var target = Path.GetFullPath(TargetPath);

        if (PathsEqual(source, target))
        {
            return Tr(
                "Hata: Kaynak ve hedef aynı klasör olamaz.",
                "Error: Source and target cannot be the same folder.");
        }

        if (IsSubPathOf(target, source))
        {
            return Tr(
                "Hata: Hedef, kaynağın içinde olamaz. Neden: Hedef tekrar taranır ve dosyalar gereksiz çoğalır.",
                "Error: Target cannot be inside source. Why: target gets scanned again and files may multiply.");
        }

        return null;
    }

    private void RebuildModeCollections()
    {
        var scopeKey = ParseExecutionScopeKey();

        OrganizationModes.Clear();
        OrganizationModes.Add(Tr("Kopyala", "Copy"));
        OrganizationModes.Add(Tr("Taşı", "Move"));
        if (string.IsNullOrWhiteSpace(SelectedOrganizationMode))
        {
            SelectedOrganizationMode = OrganizationModes[0];
        }

        DedupeModes.Clear();
        DedupeModes.Add(Tr("Karantina", "Quarantine"));
        DedupeModes.Add(Tr("Kapalı", "Off"));
        DedupeModes.Add(Tr("Sil", "Delete"));
        if (string.IsNullOrWhiteSpace(SelectedDedupeMode))
        {
            SelectedDedupeMode = DedupeModes[0];
        }

        ExecutionScopes.Clear();
        ExecutionScopes.Add(Tr("Grupla + Kopya Temizle", "Group + Duplicate Cleanup"));
        ExecutionScopes.Add(Tr("Sadece Grupla", "Group Only"));
        ExecutionScopes.Add(Tr("Sadece Kopya Temizle", "Duplicate Cleanup Only"));

        SelectedExecutionScope = scopeKey switch
        {
            ScopeGroupOnly => ExecutionScopes[1],
            ScopeDedupeOnly => ExecutionScopes[2],
            _ => ExecutionScopes[0]
        };
    }

    private void ApplyLanguage()
    {
        PageTitle = Tr("FileGrouper Kontrol Merkezi", "FileGrouper Control Center");
        PageSubtitle = Tr(
            "Tarama, filtreleme, kopya temizleme, benzer foto analizi, raporlama ve geri alma tek ekranda.",
            "Scan, filter, dedupe, similar photo analysis, reporting, and undo in one screen.");
        LanguageLabel = Tr("Dil:", "Language:");
        SafeModeLabel = Tr("Önce Test Et (Önerilen):", "Test First (Recommended):");
        DryRunOnText = Tr("Açık", "On");
        DryRunOffText = Tr("Kapalı", "Off");
        PauseButtonText = Tr("Duraklat", "Pause");
        CancelButtonText = Tr("İptal", "Cancel");
        UndoButtonText = Tr("Son İşlemi Geri Al", "Undo Last");
        ExportReportButtonText = Tr("Rapor Dışa Aktar", "Export Report");

        WorkspaceTitle = Tr("Çalışma Alanı", "Workspace");
        WorkspaceSubtitle = Tr("Kaynak ve hedef klasörleri seçin.", "Choose source and target folders.");
        SourceFolderLabel = Tr("Kaynak Klasör", "Source Folder");
        TargetFolderLabel = Tr("Hedef Klasör", "Target Folder");
        SourceWatermark = Tr("örn. /Volumes/Diskim", "e.g. /Volumes/MyDrive");
        TargetWatermark = Tr("örn. /Volumes/Diskim_Organized", "e.g. /Volumes/MyDrive_Organized");
        BrowseButtonText = Tr("Gözat", "Browse");
        OrganizationModeLabel = Tr("Düzenleme Modu", "Organization Mode");
        DuplicateModeLabel = Tr("Kopya Modu", "Duplicate Mode");
        ExecutionScopeLabel = Tr("Çalışma Kapsamı", "Execution Scope");
        PreviewButtonText = Tr("Önizleme Analizi", "Preview Analysis");
        ApplyButtonText = Tr("Seçili İşlemi Uygula", "Apply Selected Operation");
        SwapButtonText = Tr("Kaynak/Hedef Yer Değiştir", "Swap Source/Target");

        OperationOutputTitle = Tr("İşlem Özeti", "Operation Output");
        OperationOutputLine1 = Tr(
            "Gruplama: Dosyaları tür ve tarihe göre hedefe kopyalar/taşır.",
            "Grouping: Organizes files by type and date to target.");
        OperationOutputLine2 = Tr(
            "Kopya Temizleme: Karantina güvenli taşır, Sil doğrudan kaldırır.",
            "Duplicate cleanup: Quarantine moves safely, Delete removes directly.");

        QuickStartTitle = Tr("3 Adımda Kullanım", "3-Step Use");
        QuickStartLine1 = Tr("1) Kaynak klasörü seç.", "1) Select source folder.");
        QuickStartLine2 = Tr("2) Hedef klasörü seç (kaynağın dışında).", "2) Select target folder (outside source).");
        QuickStartLine3 = Tr("3) Önizleme yap, sonra uygula.", "3) Run preview, then apply.");

        PathValidationTitle = Tr("Yol Kontrolü", "Path Check");
        ProgressTitle = Tr("İlerleme", "Progress");
        AdvancedTitle = Tr("Gelişmiş", "Advanced");
        FiltersTitle = Tr("Filtreler", "Filters");
        IncludeExtLabel = Tr("Sadece uzantılar", "Include extensions");
        ExcludeExtLabel = Tr("Hariç uzantılar", "Exclude extensions");
        MinSizeLabel = Tr("Min boyut (MB)", "Min size (MB)");
        MaxSizeLabel = Tr("Max boyut (MB)", "Max size (MB)");
        FromDateLabel = Tr("Başlangıç tarihi", "From date");
        ToDateLabel = Tr("Bitiş tarihi", "To date");
        ExcludeHiddenLabel = Tr("Gizli dosyaları atla", "Skip hidden files");
        ExcludeSystemLabel = Tr("Sistem dosyalarını atla", "Skip system files");
        SimilarImagesLabel = Tr("Benzer görselleri bul", "Find similar images");

        ProfilesTitle = Tr("Profiller", "Profiles");
        ProfileNameLabel = Tr("Yeni profil adı", "New profile name");
        SaveProfileButtonText = Tr("Profili Kaydet", "Save Profile");
        ApplyProfileButtonText = Tr("Profili Uygula", "Apply Profile");

        TotalFilesLabel = Tr("Toplam Dosya", "Total Files");
        TotalSizeLabel = Tr("Toplam Boyut", "Total Size");
        DuplicateFilesLabel = Tr("Kopya Dosya", "Duplicate Files");
        ReclaimableLabel = Tr("Kazanılabilir Alan", "Reclaimable");
        ErrorsLabel = Tr("Hatalar", "Errors");
        DuplicateGroupsTitle = Tr("Kopya Grupları", "Duplicate Groups");
        LogStreamTitle = Tr("Log Akışı", "Log Stream");
        ClearButtonText = Tr("Temizle", "Clear");
        BusyLabel = Tr("Çalışıyor", "Busy");
        ErrorPrefix = Tr("HATA", "ERROR");
        SourceDialogTitle = Tr("Kaynak klasörü seçin", "Select source folder");
        TargetDialogTitle = Tr("Hedef klasörü seçin", "Select target folder");
        NonLocalPathStatus = Tr("Seçilen klasör yerel bir yol değil.", "Selected folder is not a local path.");

        UpdateSummaryLabels();
        UpdateModeExplanation();
        UpdatePathValidationInfo();
    }

    private void UpdateSummaryLabels()
    {
        GroupsSummary = $"{Tr("Gruplar", "Groups")}: {DuplicateGroups}";
        CopiedSummary = $"{Tr("Kopyalandı", "Copied")}: {FilesCopied}";
        MovedSummary = $"{Tr("Taşındı", "Moved")}: {FilesMoved}";
        QuarantinedSummary = $"{Tr("Karantina", "Quarantined")}: {DuplicatesQuarantined}";
        LastRunDisplay = LastRunAt.HasValue
            ? $"{Tr("Son çalışma", "Last run")}: {LastRunAt.Value:yyyy-MM-dd HH:mm:ss}"
            : $"{Tr("Son çalışma", "Last run")}: -";
    }

    private void UpdateModeExplanation()
    {
        var modeText = IsDryRun
            ? Tr(
                "Test modu açık: Dosyalara dokunulmaz. Sadece ne olacağını görürsün.",
                "Test mode is on: Files are not touched. You only preview actions.")
            : Tr(
                "Gerçek mod: Seçtiğin işlemler dosyalara uygulanır.",
                "Live mode: Selected actions are applied to files.");

        var scopeText = ParseExecutionScopeKey() switch
        {
            ScopeGroupOnly => Tr("Kapsam: Sadece gruplama çalışır.", "Scope: Grouping only."),
            ScopeDedupeOnly => Tr("Kapsam: Sadece kopya temizleme çalışır.", "Scope: Duplicate cleanup only."),
            _ => Tr("Kapsam: Gruplama ve kopya temizleme birlikte çalışır.", "Scope: Grouping and duplicate cleanup together.")
        };

        ModeExplanationText = $"{modeText} {scopeText}";
    }

    private void UpdatePathValidationInfo()
    {
        var pathError = GetPathValidationError();
        if (pathError is not null)
        {
            PathValidationText = pathError;
            return;
        }

        PathValidationText = ScopeIncludesGrouping()
            ? Tr(
                "Yol ayarı uygun. Hedef klasör ayrı bir konumda.",
                "Path setup looks valid. Target is separate.")
            : Tr(
                "Yol ayarı uygun. Bu modda hedef klasör zorunlu değil.",
                "Path setup looks valid. Target folder is optional in this mode.");
    }

    partial void OnSelectedLanguageChanged(string value)
    {
        var isMove = IsMoveSelection(SelectedOrganizationMode);
        var dedupe = ParseDedupeMode();
        var scope = ParseExecutionScopeKey();

        ApplyLanguage();
        RebuildModeCollections();
        SelectedOrganizationMode = isMove ? OrganizationModes[1] : OrganizationModes[0];
        SelectedDedupeMode = dedupe switch
        {
            DedupeMode.Off => DedupeModes[1],
            DedupeMode.Delete => DedupeModes[2],
            _ => DedupeModes[0]
        };
        SelectedExecutionScope = ScopeLabelFromKey(scope);

        PauseResumeButtonText = IsPaused ? Tr("Devam Et", "Resume") : Tr("Duraklat", "Pause");
        Status = Tr("Dil değiştirildi.", "Language changed.");
    }

    partial void OnIsDryRunChanged(bool value) => UpdateModeExplanation();
    partial void OnSelectedExecutionScopeChanged(string value)
    {
        UpdateModeExplanation();
        UpdatePathValidationInfo();
    }

    partial void OnSourcePathChanged(string value) => UpdatePathValidationInfo();
    partial void OnTargetPathChanged(string value) => UpdatePathValidationInfo();
    partial void OnDuplicateGroupsChanged(int value) => UpdateSummaryLabels();
    partial void OnFilesCopiedChanged(int value) => UpdateSummaryLabels();
    partial void OnFilesMovedChanged(int value) => UpdateSummaryLabels();
    partial void OnDuplicatesQuarantinedChanged(int value) => UpdateSummaryLabels();
    partial void OnLastRunAtChanged(DateTimeOffset? value) => UpdateSummaryLabels();

    public string Tr(string turkish, string english)
    {
        return SelectedLanguage.Equals("English", StringComparison.OrdinalIgnoreCase) ? english : turkish;
    }

    public static OperationSummary BuildOperationSummary(
        IReadOnlyList<FileRecord> files,
        IReadOnlyList<DuplicateGroup> duplicateGroups)
    {
        var duplicateFiles = duplicateGroups.Sum(g => g.Files.Count - 1);
        var duplicateBytes = duplicateGroups.Sum(g => g.SizeBytes * (g.Files.Count - 1));

        return new OperationSummary
        {
            TotalFilesScanned = files.Count,
            TotalBytesScanned = files.Sum(f => f.SizeBytes),
            DuplicateGroupCount = duplicateGroups.Count,
            DuplicateFilesFound = duplicateFiles,
            DuplicateBytesReclaimable = duplicateBytes
        };
    }

    private static bool PathsEqual(string a, string b)
    {
        var normalizedA = Path.GetFullPath(a).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var normalizedB = Path.GetFullPath(b).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return string.Equals(normalizedA, normalizedB, StringComparison.OrdinalIgnoreCase);
    }

    private static bool IsSubPathOf(string candidatePath, string rootPath)
    {
        var candidate = Path.GetFullPath(candidatePath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        var root = Path.GetFullPath(rootPath).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar) + Path.DirectorySeparatorChar;
        return candidate.StartsWith(root, StringComparison.OrdinalIgnoreCase);
    }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        decimal display = bytes;
        var unit = 0;

        while (display >= 1024 && unit < units.Length - 1)
        {
            display /= 1024;
            unit++;
        }

        return $"{display:0.##} {units[unit]}";
    }

    private static List<string> ParseExtensions(string value)
    {
        return value.Split([',', ';', ' '], StringSplitOptions.RemoveEmptyEntries)
            .Select(ScanFilterOptions.NormalizeExtension)
            .Where(x => !string.IsNullOrWhiteSpace(x))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    private static long? ParseSizeMb(string value)
    {
        if (!decimal.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out var mb))
        {
            if (!decimal.TryParse(value, NumberStyles.Any, CultureInfo.CurrentCulture, out mb))
            {
                return null;
            }
        }

        if (mb < 0)
        {
            return null;
        }

        return (long)(mb * 1024 * 1024);
    }

    private static DateTime? ParseDateUtc(string value)
    {
        if (DateTime.TryParse(value, out var dt))
        {
            return dt.ToUniversalTime();
        }

        return null;
    }

    private static string ToMbText(long? bytes)
    {
        if (!bytes.HasValue)
        {
            return string.Empty;
        }

        var mb = bytes.Value / 1024m / 1024m;
        return mb.ToString("0.##", CultureInfo.InvariantCulture);
    }

    private static void RunOnUi(Action action)
    {
        Dispatcher.UIThread.Post(action);
    }
}
