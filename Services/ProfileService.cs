using FileGrouper.Models;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace FileGrouper.Services;

public sealed class ProfileService
{
    private readonly string _profilePath;
    private static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    public ProfileService(string? profilePath = null)
    {
        _profilePath = profilePath ?? GetDefaultPath();
        EnsureSeedProfiles();
    }

    public IReadOnlyList<OperationProfile> LoadProfiles()
    {
        if (!File.Exists(_profilePath))
        {
            return SeedProfiles();
        }

        var json = File.ReadAllText(_profilePath);
        return JsonSerializer.Deserialize<List<OperationProfile>>(json) ?? SeedProfiles();
    }

    public void SaveProfiles(IReadOnlyList<OperationProfile> profiles)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_profilePath)!);
        var json = JsonSerializer.Serialize(profiles, JsonOptions);
        File.WriteAllText(_profilePath, json);
    }

    public void UpsertProfile(OperationProfile profile)
    {
        var profiles = LoadProfiles().ToList();
        var idx = profiles.FindIndex(x => x.Name.Equals(profile.Name, StringComparison.OrdinalIgnoreCase));
        if (idx >= 0)
        {
            profiles[idx] = profile;
        }
        else
        {
            profiles.Add(profile);
        }

        SaveProfiles(profiles);
    }

    private void EnsureSeedProfiles()
    {
        if (File.Exists(_profilePath))
        {
            return;
        }

        SaveProfiles(SeedProfiles());
    }

    private static List<OperationProfile> SeedProfiles()
    {
        return
        [
            new OperationProfile
            {
                Name = "Standard Safe",
                ExecutionScope = "GroupAndDedupe",
                OrganizationMode = OrganizationMode.Copy,
                DedupeMode = DedupeMode.Quarantine,
                IsDryRun = true,
                DetectSimilarImages = false,
                Filter = new ScanFilterOptions()
            },
            new OperationProfile
            {
                Name = "Photo Cleanup",
                ExecutionScope = "GroupAndDedupe",
                OrganizationMode = OrganizationMode.Copy,
                DedupeMode = DedupeMode.Quarantine,
                IsDryRun = true,
                DetectSimilarImages = true,
                Filter = new ScanFilterOptions
                {
                    IncludeExtensions = [".jpg", ".jpeg", ".png", ".webp", ".heic"]
                }
            },
            new OperationProfile
            {
                Name = "Aggressive Move",
                ExecutionScope = "GroupAndDedupe",
                OrganizationMode = OrganizationMode.Move,
                DedupeMode = DedupeMode.Delete,
                IsDryRun = true,
                DetectSimilarImages = false,
                Filter = new ScanFilterOptions()
            }
        ];
    }

    private static string GetDefaultPath()
    {
        var appData = Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData);
        return Path.Combine(appData, "FileGrouper", "profiles.json");
    }
}
