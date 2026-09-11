import csv
import os
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import Button, Input, Label

# Define the column names (you can modify this list as needed)
COLUMN_NAMES = ["Name", "Age", "City"]
CSV_FILE = 'records.csv'

# Initialize CSV file if it doesn't exist
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(COLUMN_NAMES)

class FormApp(App):
    inputs = {}

    def compose(self) -> ComposeResult:
        container = Container()
        
        for column in COLUMN_NAMES:
            label = Label(f"{column}:")
            input_field = Input(id=column.lower())
            self.inputs[column] = input_field
            yield Horizontal(label, input_field)

        yield Button("Submit", id="submit")
        yield Button("Quit", id="quit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "submit":
            row = []
            for column in COLUMN_NAMES:
                input_value = self.inputs[column].value
                row.append(input_value)

            with open(CSV_FILE, 'a', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(row)

            # Clear the inputs
            for input_field in self.inputs.values():
                input_field.value = ""

        elif event.button.id == "quit":
            self.exit()

if __name__ == "__main__":
    FormApp().run()

    f = FormApp()
    f.run()
