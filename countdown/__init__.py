"""The pages, their drawing and the FPP output for fpp-showmarquee.

  timecalc.py   which moment to count to, and what the number reads
  message.py    the countdown message as number and text pieces
  render.py     Pillow drawing of the countdown, centered
  still.py      the still pages (weather, show prep, schedule, messages) and how long each holds
  weather.py    Open-Meteo poller, Tempest listener, the weather page
  symbols.py    the weather symbols and holiday pictures, drawn in code
  social.py     the social media screens and logos
  showprep.py   the show prep page and its QR code
  schedule.py   show nights and times, the schedule page
  messages.py   custom messages: fill-ins, date windows, pages
  fonts.py      finding fonts, with a fallback
  output.py     the overlay buffer writer, model on/off
"""
