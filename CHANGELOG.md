# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
versioning is [semantic](https://semver.org/).

## [Unreleased]

## [0.8.0] - 2026-09-11

### Added

- A full-screen view, on `w` only: the cover centred and as large as the terminal
  allows, and a bar with the track, the controls, the seek bar and the queue's button.
  `tab` puts the queue beside the cover, and the queue's keys (`g`, `d`,
  `alt+↑↓`, `m`, `f`) work in it; `?` lists the view's keys alone; `w` again or `esc` comes back. It follows the palette and
  the theme's frame, and a pixel cover in it hides under any window opened over it.
- Autoplay (`autoplay`, Autoplay in the settings window, off by default): when the
  queue runs out, TIDAL's radio for the last track goes on the end of it and plays,
  instead of stopping. The queue is kept, and the station leaves out the seed and
  whatever the queue already has; a radio with nothing new stops as before.
- A third cover shape, `rounded`: the square cover with rounded corners, the radius in
  proportion to the side so it still shows in blocks.
- Playback speed over MPRIS: `Rate` is now writable, between `MinimumRate` 0.25 and
  `MaximumRate` 2, and announced when it changes. A desktop's rate lands on the
  nearest quarter; 0 is ignored, as the specification asks.
- Sorting in the library: `s` in a level opens a list of the orders it has, both
  ways round. Favourite tracks sort by date added, name, artist or album; favourite
  albums by date added, name, artist or release; favourite artists by date added or
  name; your playlists by date created or name; a playlist's tracks like favourite
  tracks. TIDAL does the sorting, so the whole collection is in order and not just
  the page on screen. Inside an album or an artist, which TIDAL does not sort, the
  tracks are sorted locally. The order is remembered per level, across sessions
  (in `~/.local/state/tidalamp/library-orders.json`), and the title says which one
  is on.
- Removing from the library: `d` (or Delete) takes the row out of where it is, your
  favourites or the playlist you have open, after asking with the cursor on Cancel.
  The row leaves the list at once, and so does a favourite removed with `F` from
  its own level. Only your own playlists can be changed; a track is found by its
  id, so a playlist shown sorted loses the right one.

### Changed

- `q` asks before quitting, with the cursor on Cancel; `q` again confirms. It sits next
  to `w`, and a slip from the full-screen key used to close the player. `ctrl+c` quits
  at once, without asking.
- The full-screen view's bar has a row of air above and below its controls.

- Windows opened over the full-screen view are opaque, even with transparency on.
  Under them lies a cover as large as the terminal, and a see-through window sent its
  rows again with that cover blended in at the sides on every change: on a 4K terminal
  with the cover in blocks, about four times the bytes to open the help and to scroll
  it. Over the player, windows keep their transparency.

- Pixel covers cost far less, in the player and above all in full screen. The sixel
  encoder works a band and a colour at a time in C and writes the same bytes about nine
  times faster (a 4K full-screen cover took 29 s); full screen stops a sixel cover at
  the 1280 px TIDAL serves, past which it was only stretched (now 2.7 MB in 0.9 s). kitty
  gets the picture at its own size and scales it itself, instead of a copy stretched
  first, and full screen asks TIDAL for the 1280 px cover rather than the queue's 320.

- Covers drawn with half blocks are sharper, in the player and above all in full
  screen. Each cell's two colours are chosen from every way of splitting its four
  pixels, not by brightness alone, so an edge between two colours of about the same
  brightness no longer comes out as one muddy average; and the picture is sampled
  down with LANCZOS. The cells are worked out in the thread that fetches the cover,
  so a large cover never holds up the interface.

- Quality, Hi-res rates in PipeWire and Restart PipeWire are chosen from a list in
  the settings window. The arrows no longer touch those three rows: a stray one used
  to change the quality, rewrite PipeWire's rates or restart PipeWire and cut the
  audio. Enter opens the list, and Restart's opens on Cancel, so a double Enter by
  reflex cuts nothing.
- The browser's footer lists only `? help` and `esc close`. `?` opens the help window
  with the browser's keys alone; the footer that tried to list them all dropped half
  of them on any terminal narrower than the list.

## [0.7.0] - 2026-09-11

### Added

- A tenth themed look, `bosque`: leaf green on moss, a rounded frame with a vine of
  leaves along the top and one set into its foot, the queue's heading written on its
  rule, and an original picture behind the queue: a tree and sprouts on half a globe.
  Its palette works under any layout, and its picture can be borrowed with
  `backdrop = "bosque"`.
- Playback speed: `b` (or the new speed button in the transport) opens a window
  with 0.25× to 2× in quarters, 1× as recorded. The button shows the current speed
  and lights up off 1×; mpv keeps the pitch. The speed survives an mpv restart and
  lasts until you quit. The compact player leaves the button out but keeps the key.
- A Cover shape setting (`cover_shape`): `square`, or `round` to draw the cover as a
  disc under any theme. The corners take the band's colour, so it looks the same in
  kitty, sixel and blocks, and it changes on screen at once.
- Theme and palette names follow the language: in English `bosque` reads as
  forest, `pirata` as pirate, `unidad-morada` as purple-unit, and so on, in the
  settings window and the status line. `config.toml` keeps the same names in both
  languages, so a file written under one still works under the other.
- `tidalamp/emblems/NOTICE`: the themed looks' pictures are fan tributes, their
  characters belong to their owners and the GPL does not cover them. The README's
  licence section says so too.

### Changed

- The themed looks have finer frames. Each title bar is a pattern of its own instead of
  one repeated glyph (hazard stripes, waves, a notebook's dotted rule, a flickering
  neon tube, a double border with diamonds, waves with notes, the four suits, an iron
  railing, noise), and each frame but the notebook's carries a small flourish centred
  in its foot. Reggae's notes are green and red along its gold waves, and red,
  gold and green in its foot.

### Fixed

- Counting down (`t`) broke the clock apart: the minus made the time one glyph
  wider than the clock, the rows wrapped, and the digits came out in pieces over the
  track's details. The minus is now one column against the first digit, so
  `-15:00` fits where `15:00` did.
- The queue's picture came out ringed with dark blocks in `nova` and `cuaderno`: it
  was blended into the display's ground, and those two paint the queue on the panel,
  so every cell the picture's edge only partly covered took the wrong colour. It is
  now blended into the ground the queue is actually painted on.
- In split, `nova` and `cuaderno` left half a row of black under the rule below the
  lyrics: the rule is the pane's own border, drawn on the pane's dark ground, over a
  band painted as the panel. The pane now takes the band's ground.

## [0.6.0] - 2026-09-11

### Added

- Nine themed looks, each a layout with a palette of the same name: `unidad-morada`,
  `pirata`, `cuaderno`, `neon-noir`, `runas`, `reggae`, `comodin`, `gotico` and
  `death-metal`. Choosing one in the settings window sets its palette once; the palette
  stays free afterwards, and each of the nine palettes can be used under any layout.
- Each themed look has a picture and a line that nods to what it is based on. The
  picture is drawn behind the queue the way a cover is drawn, four pixels to a cell,
  set against the right edge and under a dark veil so the rows on top still read,
  and it is there the whole time, stacked or split; the line takes the title's place
  while nothing plays. Needs Pillow, like the cover.
- A Queue backdrop setting (`backdrop`): the theme's picture (`auto`), none, or any
  themed look's, so pictures, themes and palettes can be mixed freely. Choosing a
  themed look sets both its palette and its picture once.
- `arrangement = "split"`: the queue in a column to the right of the player, with the
  playing track's lyrics above the cover (following the sung line when they are timed)
  and the transport across both columns. Switchable live from the settings window
  without interrupting playback or moving the queue's cursor. It needs at least 160×26
  and falls back to the stacked arrangement on its own where it does not fit.
- Search in the help window: `/` opens a box under the page and narrows the tab you are
  on as you type, keeping each match under its section's heading. The footer shows the
  key.

### Changed

- The cover has air inside its band: a row above and below it and two cells off the
  frame, where it used to sit flush against the border.
- A line in the player that does not fit its room (artist, album, the `SRC` and `OUT`
  lines, the title) now glides: it holds, slides slowly until its end is in view,
  holds and slides back, instead of being cut off. The title no longer loops.
- Lyrics without timestamps move through the track in the split view's pane: the
  window slides from the first line to the last as the song goes, so the end of the
  words is on screen by the end of it. They used to show from the top and stay there.
- The seek bar is a line with a dot riding on it, the played part drawn heavier in the
  accent, with a row of space on each side; the thumb used to be a full block.
- Internal: `screens.py` is a package with one module per window, the analyser and
  the moving text left `widgets.py`, the stylesheet is five files read in order, and
  the app tests are split by topic. Code moved, nothing changed.

### Fixed

- Moving the cursor through the queue no longer redraws and resends the whole list,
  only the two rows that change; the list scrolls by half a screen when the cursor
  leaves it instead of a row at a time. With a themed picture behind the queue on a
  4K terminal this cut what a keypress sends to the terminal from about 245 KiB to
  under 5.
- Leaving the split arrangement could leave a kitty cover drawn where the player's
  column used to be: the band moved without always changing size, and the old
  placement was never deleted. The cover is now taken down and put back in its new
  place.
- A kitty or sixel cover could end up painted over an open window: one that arrived
  while a window was open (a track changed from the browser, or the theme changed in
  the settings, which fetches the cover again) went up over it if another cover had
  already been taken down for that window. It now waits for the window to close.
- Switching from split back to stacked left the queue heading's key hints halfway
  across the row, measured for the half it had just left.

## [0.5.1] - 2026-09-10

### Changed

- A hi-res track now streams with a real buffer in front of it. `--cache=auto`
  decides from the playlist, and a hi-res track's playlist is a local file, so
  mpv called the whole stream local and turned the cache off: 6 Mbit/s of FLAC
  was arriving behind a one-second readahead, with an input rate exactly equal
  to the bitrate. The cache is now asked for explicitly. Measured on a 176.4
  kHz track: 1.02 s buffered before, 29.8 s after. This is headroom against a
  slow network, not a fix for any reported dropout: the stuttering that led us
  here turned out to be a USB cable negotiating full speed.

### Fixed

- The `OUT` badge reported the previous track's sample rate. It read the sink a
  quarter second after handing the URL to mpv, but PipeWire only switches the
  graph rate once mpv opens the device, which happens after the stream has been
  fetched and decoded. The badge said 44.1 kHz while the DAC's own screen read
  96K. It now follows the sink until it settles.

## [0.5.0] - 2026-09-10

### Fixed

- **Switching theme put the cover over the seek bar.** The display band's height was
  only recomputed when the cover changed size, and each layout carries different
  padding: on a theme change the band kept the previous one's height and the image
  overflowed by a row. Since a graphical protocol does not clip to its widget but paints
  over what is below, that row landed on the bar. It showed most in `nova`, and also
  when starting up with that theme already chosen: the layout class is applied before
  the styles are recomputed, so the first measurement saw no padding and the second
  resized nothing. The height is now recomputed every time.

### Changed

- **Cover art in `blocks` mode has twice the horizontal resolution.** It was drawn with
  `▀`, which spends a whole cell's width on a single pixel, and that is why covers
  looked stretched. It now uses the quadrant glyphs (`▘▝▖▗▚▞…`), which carry four
  samples per cell: two across and two down. A cell still holds only two colours, so
  where its four pixels disagree they are split into a light group and a dark one and
  each is averaged; on a photograph neighbouring pixels rarely disagree by much. The
  glyphs come from the same ancient range as `▀` and `█`, so nothing new is asked of a
  font.

### Added

- **The space bar plays and pauses**, which is what every other player does and nothing
  in the main window was using. `x` is still first, so the transport button keeps its
  Winamp letter.

- **Undo a cleared queue.** `c` stops and `C` clears: a slipped shift wiped a queue that
  may have taken half an hour, and since it can be saved to TIDAL it is worth more than
  it was. `u` gives it back, with the cursor where it was. It does not start the music
  again: clearing stopped it, and undoing returns the list, not the sound. One level,
  and it lives in memory: closing the app in between loses it.

- **Equalizer presets**: flat, rock, pop, jazz, classical, vocal, bass and treble, on
  `p` and `P` inside the equalizer window, with the one you are on named in view. They
  apply live, the way moving a band already did. Move a band afterwards and it stops
  being that preset, because the name is worked out from the gains rather than stored: a
  stored one would go on lying until something reset it.

- **Add the track to a playlist you already have**, from the track menu. It picks the
  destination among the playlists you created — the ones you follow are not offered,
  because they cannot be written to — and sends in batches of 100. If a batch fails,
  what already went in stays and the message says how many arrived. It forgets the cache
  for the listing and for that playlist, so opening it afterwards does not show it as it
  was.

- **`m` opens the track menu on the queue row**, the same one the library opens with
  `↵`: play now, play next, the track's radio and favourites. In the library it has to
  be asked for because `↵` queues the whole level; in the queue `↵` already plays the
  row, and the menu is what carries everything else.

## [0.4.0] - 2026-09-10

### Fixed

- **The queue's heading row fell short, and in `quattro` it did not even try.** Each
  layout measured that gap with a hand-written number — 14 in one, 16 in another, none
  in `quattro` — and each stopped a different distance from the right edge. All four now
  measure the same way and reach the edge; only the filler character differs.

- **The document windows were far wider than their text.** Help, About, the lyrics and
  the settings took 85% of the screen, which on a large terminal left two thirds of the
  box empty with the text against the left edge. Each is now capped at what its longest
  line actually needs. The browser is not: it is a table and spends every cell it is
  given. On a narrow terminal nothing changes.

- **`nova` started on row zero.** Having no frame, the wordmark sat against the edge of
  the terminal; the other three get that separation from their own border. It now spends
  a row of air, which it gives back in the compact layout. Its display band also turned
  out to be a row of content shorter than the other three there.

- **In `quattro` the wordmark is centred.** Left-aligned it landed directly on top of
  the cover and the two read as stacked; `retro` looks clean at the same distance
  because its name sits in the middle and only the rule passes over the artwork. The
  queue's heading stays left, which is where this layout has nothing underneath to
  collide with.

- **The cover and the clock were one cell apart.** They read as a single block and the
  digits looked stuck to the image. Now there are two.

- **The Year column was always empty.** It was not those records missing a date in
  TIDAL: the album nested inside a track in a listing carries an id, a title and a
  cover, and no date at all, so there was no year to draw. It is now asked for
  separately, once per album rather than once per track — a queue of 100 tracks off 15
  records costs 15 requests — in the background and after the queue is on screen, and
  only if the column is on. A queue saved before this change cannot be filled in,
  because it did not record which album each track belonged to; it fixes itself on the
  next reload.

### Changed

- **The track's identity moves under the clock.** The marquee carried the number, the
  artist, the title and the length on one line, and under the clock there were five
  empty rows. Now the marquee is only the number and the title, and the artist, the
  album, the year and the length take the clock's column, one per line. The year is
  silent when the catalogue does not give it. In the compact layout the block disappears
  and the clock keeps the whole band, as before.

### Added

- **`g` goes back to the track that is playing**. If the queue's search is hiding it, it
  clears the filter first; if nothing is playing, it leaves the cursor where it is and
  explains itself in the status line.
- **`p` saves the queue as a TIDAL playlist**. It asks for the name, takes a snapshot in
  the queue's real order, sends the tracks in batches of 100 and invalidates
  `My playlists`. If a batch fails, it keeps the partial playlist and says how many
  tracks arrived instead of deleting work behind the user's back.
- **Clickable bars**: the seek bar jumps to the point clicked, and volume and balance
  take that value; the balance's centre cell lands on exactly zero.

### Fixed

- **TIDAL's 429 limits are retried again.** `tidalapi` turns the HTTP error into
  `TooManyRequests`, a type the retry helper did not recognise. It now honours
  `Retry-After`, uses the normal backoff when the header is missing, and gives up
  without freezing the interface when the wait it is told to take is over a minute.

## [0.3.0] - 2026-09-10

### Added

- **Shapes for the analyzer**, chosen from the settings window (`o`, under Appearance),
  in `config.toml` or with `TIDALAMP_VISUALIZER`: `bars` are the usual upright bars,
  `mirror` grows them up and down from a centre line, `curve` draws the contour of the
  spectrum as a line one glyph per column, and `fine` draws that same line on the
  Braille dot grid, with twice the horizontal resolution and the dots between one sample
  and the next lit as well, so it comes out as a continuous stroke rather than a row of
  loose marks. `fine` needs a font that carries Braille: almost all do, but one that
  does not draws boxes, and a terminal cannot be asked beforehand, which is why it is a
  shape you choose and not one anything falls back to. All four are drawn where the
  analyzer has always been — beside the cover, under the track details — and all four
  reach the right edge of the window; the bars used to stop at 19 and leave two thirds
  of the column empty. All four read the same frame from cava, which is now asked for
  more bands than any of them draws while each shape resamples, so switching between
  them costs a redraw and does not restart the FFT.

- **A search in the queue**, on `ctrl+f`. It opens a bar under the list, in the style of
  the browser's `/` filter: it does not cover the queue, it narrows it underneath as you
  type, and on the right it says how many tracks are left of how many. It ignores case
  and accents, requires every word to appear somewhere, and also looks in the track's
  album. The rows keep **the number they really have in the queue**: a match that comes
  out as `47` says where it is in the playing order instead of pretending to be the
  first. `↵` gives the arrows back to the list with the filter applied and `Esc` clears
  it, leaving the cursor on the track you had reached. Everything that acts on the
  selected row — `↵`, `d`, `alt+↑`, `alt+↓`, `f` — acts on that track and not on the
  place it occupies on screen. The key is rebindable like any other, as `filter_queue`.

- **`tidalamp -v` / `tidalamp --version`**: prints `tidalamp <version>` in the terminal
  and exits. The number lived only inside the interface, and whoever needs it usually
  needs it exactly when the interface will not start. It answers before anything asks
  for a session, `mpv` or a terminal of a certain size, and reads the same version the
  help screen shows.

### Changed

- **The analyzer is far cheaper on large displays.** The bars are capped at 64 bands and
  widened to cover the width, instead of multiplying and thinning as the terminal grows,
  and runs of one colour are sent to the terminal as a single escape sequence rather
  than one per cell. At 380x50 — a 4K terminal — that takes the app from **55% of a core
  to 8%** at ten frames a second. The everyday analyzer gains on a normal terminal too:
  it paints fewer runs than before.

- **The help screen becomes two tabs**: "Help" is the keys and `→` leads to "About",
  with the credits, the licence and the changes per version; `←` comes back. It used to
  be one continuous document in which all of that sat three screens below the only thing
  the window is opened to look at. Each tab remembers where it was, the title bar marks
  which one you are on, and the foot says where the remaining arrow leads.

## [0.2.0] - 2026-09-10

### Added

- **A `black` palette**: pure black ground and everything else in greys and whites. It
  is the first monochrome one, so it declares more vocabulary than the others: without
  `dark_foreground`, secondary text — status, empty lists, inactive labels, the
  equalizer's dimmed bands — fell back on the usual `foreground`, and a palette with no
  colour, where the quiet things shine as brightly as the important ones, has nothing to
  say it with. `red`, `yellow`, `green` and `blue` keep their roles (error, warning,
  playable tracks, containers) and become four greys, because the only axis here is how
  much light each thing has. A test pins that no colour in the palette has a hue.

- **A filter inside the library browser**, on `/`. It opens a bar at the foot of the
  window, in the style of a web browser's find: it does not cover the level, it narrows
  it underneath as you type, and on the right it says how many rows are left of how
  many. It filters whatever the level holds — tracks in favourites, playlists in
  `My playlists`, albums, artists or a category of results — ignores case and accents
  (`sinfonia` finds *Sinfonía*), requires every word typed to appear somewhere, and also
  looks in the track's album, which is not on the line unless that column is on. `↵`
  applies the filter and gives the arrows back to the list; `Esc` clears it and leaves
  the browser open on the row that had been reached. The `more…` row is never filtered
  out: a level is one page deep until somebody asks for the rest, and hiding the only
  way to ask would turn the filter into a lie about 766 favourites.

- The README explains how to upgrade an installation with `pipx upgrade`, including that
  the `art` extra is kept and that right after a release pip may answer "already at
  latest version" because of its index cache.

### Changed

- **Cover art changes protocol live**, without a restart. Asking for a restart was
  tolerable while this was a detail of the display; it stopped being so when
  transparency began moving that setting on its own, because whoever turned it on was
  left with a hole where the cover had been until the next launch of the very thing they
  were configuring. `_reload_art()` takes the old image down — a kitty cover is held by
  the terminal and outlives the cells it was painted in until something deletes it —
  changes the protocol and asks for it again.
- **A cover that arrives while a window is open no longer paints over it.** This happens
  with any track change made from the browser, not only when changing protocol: a pixel
  image is drawn over the text whenever it arrives. It now lands and withdraws itself if
  a modal is in front. Half-block ones stay.
- **With transparency on, the cover only offers `blocks` and `off`.** The others leave
  the list for as long as it lasts, because `kitty` and `sixel` would paint the image
  over the window and `auto` promises exactly that on a terminal that can do them.
  Turning it off brings the five modes back. The notice only appears when the change
  actually removes an image: going from `auto` to `blocks` where `auto` already was
  `blocks` changes the word on the row and nothing on the screen.
- **Transparency is an option, not an imposition.** A new `Transparency` row in the `o`
  screen (`transparency` in the file, `TIDALAMP_TRANSPARENCY` in the environment), off
  by default. Turning it on moves the cover to `blocks` automatically and the screen
  says so rather than moving a setting behind anyone's back: kitty and sixel make the
  terminal paint the image over the text, so the window would open underneath the cover.
  The notice links kitty's protocol specification, which is where that drawing order is
  documented.
- **The settings screen is grouped by subject**: Audio, Appearance and General. Ten
  settings in one column read as ten unrelated switches, with the stream's quality next
  to the colour of the borders. The list scrolls itself when the terminal is small, so
  the rows at the bottom are no longer selectable and invisible at the same time, which
  is what happened when the headings were added. The window grows with its own text
  instead of staying eleven rows in the middle of a 4K screen.
- `winamp.tcss` becomes `styles.tcss`. It holds the whole layout and the four visual
  styles, of which `retro` is only one; the old name described a skin that stopped being
  everything inside it a long time ago.
- **The windows that open over the player take the screen there is.** They were a fixed
  84x26, so on 4K they sat like a stamp in the middle of an empty field. The library,
  the lyrics and the help now take 85% of the terminal (capped at 160 columns, past
  which a track line is mostly gap) and the dialogs — search, settings, columns,
  equalizer, track menu — grow with it within what their content asks for. They still
  fit in the 60x18 minimum.
- **The player shows through.** The modals' background stopped being opaque: it is now a
  translucent scrim, and each window's frame is frosted glass rather than a solid bevel.
  A terminal cannot blur, so the scrim is what stands in for it. The project's `Screen`
  rule was unintentionally overriding the 60% Textual already applies to `ModalScreen`,
  which is why the player used to vanish entirely.
- **With a modal open, the player stops redrawing itself.** That is what makes the above
  free: with a translucent screen, every frame of the analyzer repainted the player *and*
  recomposited the whole terminal, ten times a second. Measured at 240x62 with the
  library open: **37.7% of a core animating against 0.5% with the background still** —
  less than the 8.8% it cost before any of this, when the modal was opaque. What is not
  cosmetic keeps running behind: end of track, mpv's health, MPRIS and the status line,
  which is where a favourite added from the browser is reported. A cover drawn with half
  blocks no longer withdraws when a modal opens; a kitty or sixel one still does,
  because the terminal paints it over the text and it would cover the window.
- The status line is only rewritten when it changes. It was refreshed four times a
  second whatever it said, and `Static.update()` repaints either way.

### Fixed

- The browser's hint bar fits in the window. It was one 97-cell literal inside an
  84-cell box, so the terminal cut it mid-word and left a stray `R` against the edge,
  with `R reload` and `Esc close` lost. It is now assembled from pieces and drops whole
  entries, least essential first, until the line fits: `R reload` goes before
  `Esc close`, and `f/F favourite` holds out longer than `A add all`, because `A` can be
  guessed from `a` and favourites cannot be guessed from anywhere.

## [0.1.1] - 2026-09-09

A documentation and first-contact release: what someone installing tidalamp outside Arch
saw was written for Arch. Nothing about playback changes.

### Added

- When `mpv` or `cava` is missing, the message names the install command of the
  distribution being run, read from `/etc/os-release`. It used to say `pacman -S mpv`
  everywhere, so the first thing anyone installing it on Debian or Fedora saw was a
  command their system does not have. Derivatives — Mint, Pop!_OS, Nobara — are resolved
  through `ID_LIKE`, and a distribution that is not recognised gets no suggestion rather
  than a wrong one.

### Changed

- The project description stops defining itself by comparison with Winamp. The README,
  the package description, the desktop entry, the `PKGBUILD`, the CLI help and the About
  screen now talk about a retro player interface. Winamp is still named where it is a
  fact and not a label: the origin of the transport keys, the equalizer's ten bands and
  the trademark disclaimer.
- The README documents the requirements per distribution: the command for `mpv` and
  `cava` on apt, dnf, zypper and pacman, and that the Python 3.11 floor rules out
  Ubuntu 22.04 and Debian 11.
- The README is rewritten for the person using the program: a quick start and the
  installation at the top — they were half a page down — and around a hundred lines gone
  that justified design decisions to a code reviewer.
- The README's images move to absolute URLs. With relative paths none of them appeared
  on the PyPI page, which is the project's first impression.

### Fixed

- 0.1.0's PyPI page described the interface as "Winamp-style". A published version is
  immutable, so the corrected description — and the new README, and the images — could
  only arrive with this release.

## [0.1.0] - 2026-09-09

The first public release of tidalamp, distributed through PyPI and GitHub Releases. The
AUR package is ready, but publishing it is on hold while the service's public
registration for new accounts remains closed for its security hardening. The procedure
and the full status are in [`publish.md`](publish.md).

### Added

- `tidalamp` with no subcommand opens the player directly; `tidalamp tui` is kept as the
  explicit equivalent.
- A retro desktop-player TUI: seven-segment clock, scrolling title, 19-band analyzer,
  seek bar and volume and balance sliders.
- Play and pause share one button and one key (`x`), whose icon is the action it will
  perform when pressed: `▶` when stopped or paused, `‖` when playing.
- The transport takes four adjacent keys, in the order of the buttons: `z` previous,
  `x` play/pause, `c` stop, `v` next. The buttons' labels come from the effective
  bindings, so they follow `config.toml`.
- The transport is drawn as three-row buttons, in two groups: the transport on one side
  and shuffle/repeat on the other.
- The queue is drawn in columns when the terminal allows it, rather than putting the
  artist inside the title. **Which ones are shown is chosen** from the `o` window, which
  opens a picker with the eleven the TIDAL API fills in: track number, version, artist,
  album, year, quality, explicit, popularity, disc, ISRC and duration. The change
  applies to the queue already on screen, not to the next one loaded. They fall away on
  their own as the window narrows, in the order in which they can be lost, and at the
  end `artist - title` is left on one line with the duration on the right.
- **Four visual layouts, chosen with `theme`**, independent of colour: `quattro` (the
  default, flat and modern), `retro` (title bars drawn as a rule with the name centred,
  square keys packed together and the toggles spelled `SHUFFLE` and `REPEAT`), `nova`
  (frameless, one ground throughout, and an accent rule under whichever toggle is on)
  and `ascii` (a terminal from before box drawing: `[ z << ]` buttons, rules of `=` and
  `-`, and no glyph in the chrome you could not type). They are changed from the `o`
  window without stopping playback.
- **Portable palettes** as well as following Omarchy: `classic`, `tokyo-night`,
  `catppuccin`, `nord`, `gruvbox`, or a TOML of your own in
  `~/.config/tidalamp/palettes/`, in the same format as Omarchy's `colors.toml`. Any
  palette works with any of the layouts.
- The settings window warns on its own line, and in the warning colour, when PipeWire's
  graph is fixed at one rate and resamples everything: the badge tells the truth about
  the stream while the DAC receives something else, and nothing on screen gave it away
  without moving the cursor.
- Playback through a long-lived `mpv` over an IPC socket, restarted automatically if the
  process dies.
- TIDAL device-flow authentication, with no app registration, refreshing the token at
  startup and mid-session.
- A queue with shuffle, repeat in three modes, reordering and persistence between
  sessions. Both live on the transport bar as `s ⇄` and `r ↻` buttons, lit in the
  theme's accent; the bar separates transport and windows with `·` and aligns the
  windows to the right.
- A library browser: playlists, favourites, albums and artists, paginated and with the
  levels cached in memory.
- Search for tracks, albums, artists and playlists.
- A menu of actions on `↵` over a song: play now (`a`), play next (`c`), play the radio
  TIDAL generates for that track (`d`) and add to favourites (`v`), each with its icon.
- TIDAL favourites on `f` and `F`.
- A complete MPRIS2 service, `TrackList` interface included.
- Cover art in the terminal through the kitty protocol, sixel or half blocks, in a box
  that grows with the terminal (from 18×9 to 40×20) along with the analyzer.
- Synced lyrics (LRC) with a plain-text fallback.
- A ten-band equalizer and balance, as mpv filters, with persistence.
- A real spectrum through `cava` when it is installed, and an RMS meter when it is not.
- The palette taken from the active Omarchy theme, changing live.
- A `config.toml` configuration file and rebindable keys.
- A settings window (`o`) that writes that file: quality, cover art, language and
  logging, warning when an environment variable overrides them. It includes the state of
  the audio output, and enables PipeWire's hi-res rates — without which a 24/96 stream
  reaches the DAC resampled to 48 kHz — and its restart.
- The language becomes a setting in the file; before it came only from `$LANG`.
- A desktop entry and icon, and a notice when the terminal is smaller than 76×20.
- Packaging for the AUR and for PyPI, published through Trusted Publishing.
- A bilingual interface and CLI, Spanish and English, following the locale, falling back
  to Spanish.
- A help window (`?` or `h`) with every shortcut grouped and read from the effective
  bindings, so a key rebound in `config.toml` appears as the one to press. It includes
  About — version, author, repository and licence — and the summary of changes for each
  version.
- A public README in English.

### Fixed

- **Hi-res did not play.** The HLS playlist `tidalapi` generates lists the
  initialisation segment as if it were audio and emits no `#EXT-X-MAP`; on top of that
  ffmpeg blocks `https` from a local playlist. Both are resolved.
- **The default quality never produced lossless.** Asking the device-flow client for
  `LOSSLESS` returns `HIGH` every time; the default is `HI_RES_LOSSLESS`.
- **A short page from TIDAL is not the end of the list.** The library was leaving out
  676 of 766 favourite tracks.
- **`My playlists` took 20 seconds** with 110 playlists, because `tidalapi` fetched each
  one separately. It now takes 0.4 s.
- **The app would not start with an expired access token**, which is the normal case
  when opening it the next day.
- **The status bar was off screen**, so everything the application had to say was
  written where nobody could see it.
- **`c` (stop) restarted the list from the beginning**: it left mpv idle and the tick
  read that as "the track ended", so it moved on to the next one — which from a stopped
  queue is the first.
- The badge showed "16bit" over lossy audio.
- **The volume bar broke above 100.** The fill was not clamped to the track's width, so
  at 105 the number shifted, at 115 it left the widget and at 130 the line was so long
  that nothing was drawn at all: `VOL` and an empty row. The widget no longer lets any
  value deform its track, and the volume is capped at 100 — above that mpv applies
  digital gain to an already normalised signal, which clips — from the keyboard and
  from MPRIS alike.
- **Without Pillow there was no cover and no explanation**: the widget stayed hidden and
  the only trace was a `log.info` in a file. The status bar now names the extra that
  fixes it at startup, and the installation instructions from the repository include
  `".[art]"`, which is where it was missing.
- **Brackets disappeared from text we did not write.** `Static.update` reads a `str` as
  Rich markup: an album called "Lateralus [Deluxe Edition]" was drawn as "Lateralus ",
  and a name with a closing tag (`[/]`) raised `MarkupError` mid-render. The four
  `Static` widgets that receive TIDAL names, track titles or exception messages are now
  built with `markup=False`.
