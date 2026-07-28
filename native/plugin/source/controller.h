#pragma once

#include "public.sdk/source/vst/vsteditcontroller.h"

namespace Steinberg::Vst::SammyBlaze {

class Controller final : public EditController
{
public:
    static FUnknown* createInstance (void*)
    {
        return static_cast<IEditController*> (new Controller);
    }

    tresult PLUGIN_API initialize (FUnknown* context) SMTG_OVERRIDE;
    tresult PLUGIN_API setComponentState (IBStream* state) SMTG_OVERRIDE;
};

} // namespace Steinberg::Vst::SammyBlaze
