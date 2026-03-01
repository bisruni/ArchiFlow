using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using FileGrouper.ViewModels;
using System.IO;
using System.Linq;
using System.Threading.Tasks;

namespace FileGrouper.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContext = new MainWindowViewModel();
    }

    private MainWindowViewModel Vm => (MainWindowViewModel)DataContext!;

    private async void BrowseSourceClick(object? sender, RoutedEventArgs e)
    {
        var folder = await PickFolderAsync(Vm.SourceDialogTitle);
        if (folder is null)
        {
            return;
        }

        Vm.SourcePath = folder;

        if (string.IsNullOrWhiteSpace(Vm.TargetPath))
        {
            var parent = Directory.GetParent(folder)?.FullName;
            if (!string.IsNullOrWhiteSpace(parent))
            {
                Vm.TargetPath = Path.Combine(parent, $"{Path.GetFileName(folder)}_Organized");
            }
        }
    }

    private async void BrowseTargetClick(object? sender, RoutedEventArgs e)
    {
        var folder = await PickFolderAsync(Vm.TargetDialogTitle);
        if (folder is null)
        {
            return;
        }

        Vm.TargetPath = folder;
    }

    private async Task<string?> PickFolderAsync(string title)
    {
        var picked = await StorageProvider.OpenFolderPickerAsync(
            new FolderPickerOpenOptions
            {
                AllowMultiple = false,
                Title = title
            });

        var localPath = picked.FirstOrDefault()?.TryGetLocalPath();
        if (string.IsNullOrWhiteSpace(localPath))
        {
            Vm.Status = Vm.NonLocalPathStatus;
            return null;
        }

        return localPath;
    }
}
