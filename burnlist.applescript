-- Burnlist.app entry point.
-- AppleScript wrapper so macOS LaunchServices sees a proper AppleEvent handler.
-- The real work happens in Resources/launcher.sh, which bootstraps deps on first
-- run and then starts the Python server.

on launchUnderlying()
    set sh to quoted form of (POSIX path of (path to me) & "Contents/Resources/launcher.sh")
    do shell script sh & " > /dev/null 2>&1 &"
end launchUnderlying

on run
    launchUnderlying()
end run

on reopen
    -- Dock click / re-launch while the app is already running.
    -- launcher.sh detects the existing server and just opens the browser.
    launchUnderlying()
end reopen

on quit
    try
        do shell script "lsof -ti :7474 2>/dev/null | xargs kill 2>/dev/null"
    end try
    continue quit
end quit
