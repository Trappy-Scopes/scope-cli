from prompt_toolkit import prompt
from prompt_toolkit.styles import Style



def prompt_suggest(text, options):

    example_style = Style.from_dict({
        'rprompt': 'bg:#ff0066 #ffffff',
    })

    def get_rprompt():
        return str(options)

    answer = prompt(f"{text} >", rprompt=get_rprompt, style=example_style)
    return answer