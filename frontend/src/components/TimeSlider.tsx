interface TimeSliderProps {
  selectedTime: string
  onTimeChange: (time: string) => void
}

export function TimeSlider({ selectedTime, onTimeChange }: TimeSliderProps) {
  const times = [
    '06:00', '06:30', '07:00', '07:30', '08:00', '08:30', '09:00', '09:30',
    '10:00', '10:30', '11:00', '11:30', '12:00', '12:30', '13:00', '13:30',
    '14:00', '14:30', '15:00', '15:30', '16:00', '16:30', '17:00', '17:30',
    '18:00'
  ]

  return (
    <div className="time-slider-card">
      <h3>Time of Day</h3>
      <p className="selected-time">{selectedTime} IST</p>
      <input
        type="range"
        min="0"
        max={times.length - 1}
        step="1"
        value={times.indexOf(selectedTime)}
        onChange={(e) => onTimeChange(times[parseInt(e.target.value)])}
        className="slider"
      />
      <div className="slider-labels">
        <span>06:00</span>
        <span>12:00</span>
        <span>18:00</span>
      </div>
    </div>
  )
}
