using System.Collections.Concurrent;
using System.Reflection;
using MediaBrowser.Common.Api;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Controller.Entities;
using MediaBrowser.Controller.Library;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging;

namespace Themerr.Connector;

[ApiController]
[Route("Themerr")]
[Authorize(Policy = Policies.RequiresElevation)]
public sealed class Controller : ControllerBase
{
    private static readonly ConcurrentDictionary<Guid, SemaphoreSlim> Locks = new();
    private readonly ILibraryManager _library;
    private readonly ThemeFiles _themes;
    private readonly LegacyOwnership _legacy;
    private readonly ILogger<Controller> _logger;
    private static string Metadata(string key) => typeof(Plugin).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>()
        .Single(a => a.Key == key).Value!;

    public Controller(ILibraryManager library, IApplicationPaths paths, ILogger<Controller> logger)
    {
        _library = library;
        _themes = new(new ThemeOwnership(paths.DataPath));
        _legacy = new(paths.DataPath);
        _logger = logger;
    }

    [HttpGet("Connector")]
    public object Identity() => new { protocol = 1, build = Metadata("ThemerrBuild"), targetAbi = Metadata("JellyfinAbi") };

    [HttpGet("Items/{itemId:guid}/Theme")]
    public ActionResult<ThemeState> State(Guid itemId)
    {
        var item = _library.GetItemById(itemId);
        if (item is null) return NotFound();
        var root = Root(item);
        if (root is null) return BadRequest();
        try { return _themes.State(itemId, root, item.GetThemeSongs().Count); }
        catch (ThemeConflictException) { return Conflict(); }
        catch (Exception error) when (error is SqliteException or IOException or UnauthorizedAccessException)
        { return StorageFailure(error); }
    }

    [HttpPost("Items/{itemId:guid}/Theme")]
    [RequestSizeLimit(104857600)]
    public async Task<ActionResult<ThemeState>> Upload(Guid itemId, CancellationToken cancellationToken)
    {
        if (Request.Headers["X-Themerr-Connector"] != Metadata("ThemerrBuild")) return Conflict();
        var item = _library.GetItemById(itemId);
        if (item is null) return NotFound();
        var root = Root(item);
        if (root is null || (item.IsLocked && Request.Headers["X-Themerr-Ignore-Locked"] != "true")) return Conflict();
        var gate = Locks.GetOrAdd(itemId, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var state = await _themes.Save(itemId, root, Request.Body, Request.ContentType,
                Request.Headers["X-Themerr-SHA256"].ToString(), item.GetThemeSongs().Count,
                cancellationToken, Request.Headers["X-Themerr-Overwrite-User"] == "true",
                Request.Headers["X-Themerr-Backup-User"] != "false").ConfigureAwait(false);
            await item.RefreshMetadata(cancellationToken).ConfigureAwait(false);
            return state;
        }
        catch (ThemeConflictException) { return Conflict(); }
        catch (InvalidDataException) { return BadRequest(); }
        catch (Exception error) when (error is SqliteException or IOException or UnauthorizedAccessException)
        { return StorageFailure(error); }
        finally { gate.Release(); }
    }

    private ObjectResult StorageFailure(Exception error)
    {
        _logger.LogError(error, "Could not access connector theme storage.");
        return StatusCode(500, "Could not access connector theme storage.");
    }

    [HttpPost("Items/{itemId:guid}/Theme/Import")]
    public async Task<ActionResult<ThemeState>> Import(Guid itemId, CancellationToken cancellationToken)
    {
        if (Request.Headers["X-Themerr-Connector"] != Metadata("ThemerrBuild")) return Conflict();
        var item = _library.GetItemById(itemId);
        if (item is null) return NotFound();
        var root = Root(item);
        if (root is null) return BadRequest();
        var gate = Locks.GetOrAdd(itemId, _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            string? digest;
            try { digest = _legacy.Hash(itemId); }
            catch (SqliteException error)
            {
                _logger.LogWarning(error, "Could not read older Themerr ownership; existing themes remain protected.");
                digest = null;
            }
            return _themes.Import(itemId, root, digest, item.GetThemeSongs().Count);
        }
        catch (ThemeConflictException) { return Conflict(); }
        catch (Exception error) when (error is SqliteException or IOException or UnauthorizedAccessException)
        { return StorageFailure(error); }
        finally { gate.Release(); }
    }

    private static string? Root(BaseItem item) =>
        item is MediaBrowser.Controller.Entities.Movies.Movie or MediaBrowser.Controller.Entities.TV.Series or
            MediaBrowser.Controller.Entities.Movies.BoxSet &&
        item.IsFileProtocol && !item.IsInMixedFolder && Directory.Exists(item.ContainingFolderPath)
            ? Path.GetFullPath(item.ContainingFolderPath) : null;
}
