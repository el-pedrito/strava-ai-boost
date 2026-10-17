// Gate 0 page: one button per embedded .workout file, each wired to the
// SHIPPED download module (not a copy), so the device test covers the real code.
import workouts from 'virtual:gate0-workouts';
import { downloadWorkout } from '../src/lib/downloadWorkout';

const list = document.getElementById('workouts');
const status = document.getElementById('status');

if (list && status) {
  for (const workout of workouts) {
    const item = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    // textContent, never innerHTML: filenames are untrusted input.
    button.textContent = workout.name;
    button.addEventListener('click', () => {
      status.textContent = '';
      try {
        // Synchronous call inside the gesture handler: iOS requires it.
        downloadWorkout(workout.b64, workout.name);
      } catch (err) {
        status.textContent = `Erreur : ${err instanceof Error ? err.message : String(err)}`;
      }
    });
    item.appendChild(button);
    list.appendChild(item);
  }
}
