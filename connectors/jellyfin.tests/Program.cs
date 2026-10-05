using System.Security.Cryptography;
using Themerr.Connector;

var root = Path.Combine(Path.GetTempPath(), "themerr-connector-test-" + Guid.NewGuid());
Directory.CreateDirectory(root);
var bytes = "complete validated audio"u8.ToArray();
var digest = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
static void Check(bool condition) { if (!condition) throw new Exception("Connector regression check failed."); }
static async Task Reject<T>(Func<Task> action) where T : Exception
{
    try { await action(); }
    catch (T) { return; }
    throw new Exception("Expected " + typeof(T).Name);
}
Task<ThemeState> Save(string type = "audio/mp4", string? hash = null, byte[]? data = null) =>
    ThemeFiles.Save(root, new MemoryStream(data ?? bytes), type, hash ?? digest, 0, CancellationToken.None);
try
{
    await Reject<InvalidDataException>(() => Save("../../file"));
    await Reject<InvalidDataException>(() => Save(hash: new string('z', 64)));
    await Reject<InvalidDataException>(() => Save(hash: new string('a', 64)));
    await Reject<InvalidDataException>(() => Save(data: []));
    Check(!Directory.EnumerateFiles(root).Any());
    File.WriteAllText(Path.Combine(root, "theme.mp3"), "user theme");
    await Reject<ThemeConflictException>(() => Save());
    Check(File.ReadAllText(Path.Combine(root, "theme.mp3")) == "user theme");
    File.Delete(Path.Combine(root, "theme.mp3"));
    var saved = await Save();
    Check(saved.Owned && saved.Sha256 == digest);
    Check(ThemeFiles.State(root).Owned);
    Check(!ThemeFiles.State(root, 2).Owned);
    await Reject<ThemeConflictException>(() => ThemeFiles.Save(root, new MemoryStream(bytes),
        "audio/mp4", digest, 2, CancellationToken.None));
    var switched = await Save("audio/ogg");
    Check(switched.Owned && !File.Exists(Path.Combine(root, "theme.m4a")));
    Check(File.ReadAllBytes(Path.Combine(root, "theme.opus")).SequenceEqual(bytes));
    File.WriteAllText(Path.Combine(root, "theme.opus"), "manually changed");
    Check(!ThemeFiles.State(root).Owned);
    await Reject<ThemeConflictException>(() => Save());
    File.Delete(Path.Combine(root, "theme.opus"));
    File.Delete(Path.Combine(root, ".themerr-connector.json"));
    var sibling = root + "-sibling";
    Directory.CreateDirectory(sibling);
    try
    {
        var target = Path.Combine(sibling, "outside.m4a");
        File.WriteAllText(target, "outside");
        bool links = true;
        try { File.CreateSymbolicLink(Path.Combine(root, "theme.m4a"), target); }
        catch (UnauthorizedAccessException) { links = false; }
        catch (IOException error) when (OperatingSystem.IsWindows() && (error.HResult & 0xffff) == 1314)
        { links = false; }
        if (links)
        {
            await Reject<ThemeConflictException>(() => Save());
            Check(File.ReadAllText(target) == "outside");
            File.Delete(Path.Combine(root, "theme.m4a"));
            File.CreateSymbolicLink(Path.Combine(root, ".themerr-connector.json"), target);
            await Reject<ThemeConflictException>(() => Save());
            Check(File.ReadAllText(target) == "outside");
        }
        else { Console.WriteLine("Symbolic-link checks skipped: creation privilege unavailable on this host."); }
    }
    finally { Directory.Delete(sibling, true); }
    Console.WriteLine("Connector file ownership, integrity, and format checks passed.");
}
finally { Directory.Delete(root, true); }
